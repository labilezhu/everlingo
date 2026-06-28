# ref: docs/impl-spec/memory-extract-agent-spec.md
# Chat Agent -> Memory Extract Agent -> Memory Writer Agent 数据流水线中的"筛选+结构化抽取"。
# 每个 MainAgent 实例持有自己的 MemoryExtractAgent，daemon thread + queue 异步消费。

from __future__ import annotations

import logging
import queue
import re
import threading
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from ...llm import create_llm
from ...setting import load_user_doc
from .mem_entries import (
    EntryWriterProtocol,
    ExtractInput,
    ExtractLLMOutput,
    LLMGeneratedEntry,
    MemoryEntry,
)

_GMT8 = timezone(timedelta(hours=8))


logger = logging.getLogger("everlingo")


# ref: chat-agent-spec.md — *_demote_headings*
# 注入到 system prompt 的 USER.md 内容需要降级标题层级，
# 防止与 prompt 外层的 ## 标题冲突。本阶段 system prompt 外层使用 ##，
# 注入 USER.md 也使用与 Chat Agent 相同的 +2 偏移。
_HEADING_DEMOTE_OFFSET = 2


def _demote_headings(text: str) -> str:
    """把 markdown 标题降 N 级（N=_HEADING_DEMOTE_OFFSET），避免与外层 prompt 标题冲突。

    ref: chat-agent-spec.md — *.md 文件注入时标题层级处理
    """
    n = _HEADING_DEMOTE_OFFSET
    # 每行行首的 1..6 个 # 后跟空白；多于 6 个视为普通文本不处理。
    pattern = re.compile(r'^(#{1,6}) ', flags=re.MULTILINE)

    def _shift(m: re.Match[str]) -> str:
        original = m.group(1)
        new_level = min(len(original) + n, 6)
        return '#' * new_level + ' '

    return pattern.sub(_shift, text)


def _now_gmt8_str() -> str:
    """GMT+8 时间戳字符串，格式 yyyy-mm-dd HH:MM:SS。

    ref: memory-extract-agent-spec.md — 字段来源约定 · timestamp
    """
    return datetime.now(_GMT8).strftime("%Y-%m-%d %H:%M:%S")


def _render_context_messages(messages) -> str:
    """把 context_messages 序列化为 LLM 可读的多行文本。

    按发言者与内容线性展开，便于 LLM 识别本轮对话事实。
    顺序与 MainAgent._messages 一致（不含注入的 SystemMessage）。
    """
    lines: list[str] = []
    for m in messages:
        role = getattr(m, "type", "") or m.__class__.__name__
        content = getattr(m, "content", "") or ""
        if isinstance(content, list):
            # langchain 的 content 可能是 list[dict]（多模态）；退化为 str
            content = str(content)
        # 工具消息标注：ToolMessage 是查词/翻译工具返回，是 mean_summary 的事实来源
        lines.append(f"[{role}] {content}")
    return "\n".join(lines)


def _intent_mode_label(intent_mode: Optional[str]) -> str:
    """ExtractInput.intent_mode -> user_intent 字符串。

    ref: memory-extract-agent-spec.md — 字段来源约定 · user_intent
    """
    if intent_mode is None:
        return "None"
    return intent_mode


def _build_system_prompt(
    target_lang: str,
    interface_lang: str,
    channel_name: str,
    seen_headwords: list[str],
    user_doc: str,
) -> str:
    """构建 Extract Agent 的 system prompt。

    ref: docs/impl-spec/memory-extract-agent-spec.md — 实现 · System prompt 要点
    """
    seen_text = "\n".join(f"- {h}" for h in seen_headwords) if seen_headwords else "（无）"

    user_doc_section = ""
    if user_doc.strip():
        user_doc_section = (
            "\n## 用户个性化偏好 (USER.md)\n"
            "以下为 USER.md 内容，用于辅助筛选判断（如判断是否'琐碎/显而易见'、"
            "'与目标学习语言相关性'、'用户偏好类应跳过'等）。\n"
            "**仅用于筛选判断**，不要据此修改 mean_summary（mean_summary 必须保持事实性）。\n\n"
            "---\n"
            f"{_demote_headings(user_doc.strip())}\n"
            "---\n"
        )

    return f"""你是 EverLingo 的"知识点抽取器"。你的职责是分析本轮 Chat Agent 与用户的对话，判断是否有值得记入记忆库的知识点，并以结构化 JSON 输出 entries。

你**不**与用户对话。你**不**写入任何文件。输出 JSON 后流程结束。

## 会话元数据（系统提供，无需在输出中生成）

- chat_session_id: 系统提供
- channel_name: {channel_name}
- user_intent: 自动 / dict / translate（由系统从 input 传入）
- lang (目标学习语言): {target_lang}
- interface_lang (用户熟识的语言): {interface_lang}

## 输入

每轮你会收到：
- intent_mode：本轮 MainAgent 模式（None=自动 / dict / 查词 / translate / 翻译）
- context_messages：最近最多 20 轮对话片段，顺序与 Chat Agent 实际收到/产出一致。
  包含 HumanMessage（用户）/ AIMessage（Chat Agent 回复）/ ToolMessage（查词/翻译工具返回）。
  ToolMessage 的 content 是 mean_summary 的**事实来源**。

## 筛选规则（本阶段精简版）

### 规则优先级（高 → 低）

1. **用户明确要求记住** —— 最高优先级，即使知识点对用户"显而易见"也应保存。
2. **纠正事项** —— 信息源头是用户自己，且用户未预期到的，且目标学习语言方面的错误。
3. **跳过规则**（任一触发即跳过）。

### 应保存（本阶段仅两类）

1. **用户明确要求记住**：如「记住 X 这个短语」「帮我记下 X」。
2. **纠正事项**：用户自己写错的目标学习语言（如写 "I goes to school"，Chat Agent 纠正为 "I go to school"），且用户未预期到此错误。

### 应跳过（任一触发）

1. **与目标学习语言（lang={target_lang}）无关**。
2. **用户偏好类**：应入 USER.md（由 Chat Agent 通过 user_doc 工具处理），不由你抽取。
3. **原始数据转储**：单条 Message 文本超过 1000 字时，该 Message 不作为 mean_summary 的事实来源，但轮内其它知识点仍可抽取。
4. **会话内已抽取**：headword 已在下方"会话内已抽取 headword"列表中。
5. **琐碎/显而易见**。

### 本阶段不做（推迟到下一阶段）

- 推断用户需要记住
- 主动询问是否记住

## 会话内已抽取 headword

以下 headword 已在本次会话抽取过，**不要再输出**：

{seen_text}

{user_doc_section}
## 输出 schema（必须严格遵循）

你只输出以下字段（其余字段如 chat_session_id / entry_id / timestamp / channel_name / user_intent / lang 由系统填充，不要尝试生成）：

```json
{{
  "entries": [
    {{
      "item_type": "vocab | phrases | grammar | pragmatics",
      "why_want_to_save_memory": "用户明确要求记住知识点 | 纠正事项",
      "headword": "...",
      "mean_summary": "...",
      "conversation_context": "..."
    }}
  ]
}}
```

## 字段说明与真实性约束

- **item_type**：vocab（单词）/ phrases（短语）/ grammar（语法点）/ pragmatics（语用）。
- **why_want_to_save_memory**：本阶段只允许上面 schema 中列出的两个枚举值。
- **headword**：单词时为单词本身；短语则原样写出。
- **mean_summary**：必须基于 context_messages 中 ToolMessage 的事实内容（查词/翻译工具返回）。
  - 本轮无工具返回（纯问答）时，基于 Chat Agent 的回复给出的解释。
  - **不允许引入外部知识或对 USER.md 做个性化改写**。
  - 应保持事实性、简洁。
- **conversation_context**：本轮学习该知识点的对话场景（一两句话）。

## 输出格式

- 只输出合法 JSON，不输出任何解释性文字、Markdown 代码块包装或前后缀。
- 没有符合规则的知识点时，输出 `{{"entries": []}}`。
"""


class MemoryExtractAgent:
    """知识点抽取 Agent，异步执行。

    ref: docs/impl-spec/memory-extract-agent-spec.md
    - 每个 MainAgent 实例持有自己的 MemoryExtractAgent
    - daemon thread + queue.Queue 异步消费 ExtractInput
    - submit() 仅入队，不阻塞用户回复
    - 提取完成后转交 memory_writer.enqueue(entries)
    """

    def __init__(
        self,
        memory_writer: EntryWriterProtocol,
        chat_session_id: str,
        channel_name: str,
        target_lang: str,
        interface_lang: str,
    ) -> None:
        self._memory_writer = memory_writer
        self._chat_session_id = chat_session_id
        self._channel_name = channel_name
        self._target_lang = target_lang
        self._interface_lang = interface_lang

        # ref: memory-extract-agent-spec.md — 会话级状态
        # 本阶段只有 session_seen_headwords。
        self._session_seen_headwords: list[str] = []

        # ref: 实现 · 用 langchain 的 LLM 调用 + structured output
        self._llm = create_llm().with_structured_output(ExtractLLMOutput)

        self._queue: "queue.Queue[Optional[ExtractInput]]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None

    # ── 生命周期 ──────────────────────────────────────────────────────

    def start(self) -> None:
        """启动 daemon 消费线程。"""
        if self._thread is not None and self._thread.is_alive():
            return
        # daemon=True: 进程退出时直接丢弃未处理项（可接受丢失，与 Writer 一致）
        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"mem-extract-{self._chat_session_id[:8]}",
            daemon=True,
        )
        self._thread.start()

    def submit(self, extract_input: ExtractInput) -> None:
        """入队即返回，不阻塞。

        ref: memory-extract-agent-spec.md — 异步执行
        """
        self._queue.put(extract_input)

    def stop(self, timeout: float = 1.0) -> None:
        """发送结束哨兵并等待线程退出。供测试使用。"""
        self._queue.put(None)
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    # ── 主循环 ────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        """消费 ExtractInput；遇到 None 哨兵退出。"""
        while True:
            item = self._queue.get()
            if item is None:
                return
            try:
                self._extract(item)
            except Exception:
                # ref: 失败处理 —— logger.exception 后丢弃本轮 entries，不调 enqueue
                logger.exception(
                    "memory extract failed for chat_session_id=%s",
                    self._chat_session_id,
                )

    # ── 单轮抽取（可被测试直接调用以同步化断言）─────────────────────

    def _extract(self, extract_input: ExtractInput) -> list[MemoryEntry]:
        """执行一次抽取，返回构造好的 MemoryEntry 列表（可能为空）。

        成功路径：返回 entries，调用方负责日志输出与转交 memory_writer。
        异常路径：调用方 _run_loop 已捕获，本函数仍允许异常向上传播。

        公开成方法是为便于测试以同步方式验证 post-process 行为。
        """
        user_doc = load_user_doc()
        system_prompt = _build_system_prompt(
            target_lang=self._target_lang,
            interface_lang=self._interface_lang,
            channel_name=self._channel_name,
            seen_headwords=self._session_seen_headwords,
            user_doc=user_doc,
        )

        intent_label = _intent_mode_label(extract_input.intent_mode)
        context_text = _render_context_messages(extract_input.context_messages)
        user_msg = (
            f"intent_mode: {intent_label}\n\n"
            f"context_messages (chronological, most recent last):\n"
            f"{context_text}\n\n"
            "请按 system prompt 中的筛选规则与 schema 输出 JSON。"
        )

        # ref: 实现 — 用 langchain 的 LLM 调用 + structured output
        result: ExtractLLMOutput = self._llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_msg),
        ])

        entries = self._post_process(result.entries, intent_label)

        # 累积 seen headwords（仅当 LLM 输出被采纳的 entries）
        for e in entries:
            if e.headword not in self._session_seen_headwords:
                self._session_seen_headwords.append(e.headword)

        # ref: 日志要求 — 每个 entry info 日志输出全部字段
        for e in entries:
            logger.info(
                "memory extract entry: entry_id=%s chat_session_id=%s timestamp=%s "
                "channel_name=%s item_type=%s why=%s user_intent=%s lang=%s "
                "headword=%s mean_summary=%r conversation_context=%r",
                e.entry_id, e.chat_session_id, e.timestamp,
                e.channel_name, e.item_type, e.why_want_to_save_memory,
                e.user_intent, e.lang,
                e.headword, e.mean_summary, e.conversation_context,
            )

        # 非空才转交 writer
        if entries:
            self._memory_writer.enqueue(entries)

        return entries

    def _post_process(
        self, llm_entries: list[LLMGeneratedEntry], user_intent: str
    ) -> list[MemoryEntry]:
        """把 LLM 输出覆盖透传字段并补全 entry_id / timestamp。"""
        ts = _now_gmt8_str()
        out: list[MemoryEntry] = []
        for raw in llm_entries:
            out.append(MemoryEntry(
                entry_id=str(uuid.uuid4()),
                timestamp=ts,
                chat_session_id=self._chat_session_id,
                channel_name=self._channel_name,
                user_intent=user_intent,
                lang=self._target_lang,
                item_type=raw.item_type,
                why_want_to_save_memory=raw.why_want_to_save_memory,
                headword=raw.headword,
                mean_summary=raw.mean_summary,
                conversation_context=raw.conversation_context,
            ))
        return out


def make_default_extract_agent(
    chat_session_id: str,
    channel_name: str,
    target_lang: str,
    interface_lang: str,
) -> MemoryExtractAgent:
    """便利构造器：使用 gateway 模块级的 memory_writer 单例。

    ref: docs/impl-spec/memory-extract-agent-spec.md — 生命周期与状态
    Extract Agent 持有全局 memory_writer 引用，用于转交 entries。

    延迟导入 gateway 避免 agent -> mem_extract -> gateway -> session -> agent 循环。
    """
    from ...gateway.gateway import memory_writer
    return MemoryExtractAgent(
        memory_writer=memory_writer,
        chat_session_id=chat_session_id,
        channel_name=channel_name,
        target_lang=target_lang,
        interface_lang=interface_lang,
    )
