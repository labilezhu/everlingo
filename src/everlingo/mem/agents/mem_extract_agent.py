# ref: docs/impl-spec/memory-extract-agent-spec.md
# Chat Agent -> Memory Extract Agent -> Memory Writer Agent 数据流水线中的"筛选+结构化抽取"。
# 每个 MainAgent 实例持有自己的 MemoryExtractAgent，daemon thread + queue 异步消费。
#
# 2026-07 迁移：system prompt 改为通过 MCP compile_prompt 工具读取
# vault 中 spec/memory_extract_spec.md（含 include 展开），
# indexer 离线时本轮 extract 失败丢弃（与 LLM call 失败一致），不再本地兜底。

from __future__ import annotations

import asyncio
import logging
import queue
import re
import threading
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from everlingo.utils.md_prompt_compiler import shift_headings

from ...llm import create_extract_llm
from ...setting import load_user_doc

from .mem_entries import (
    EntryWriterProtocol,
    ExtractInput,
    ExtractLLMOutput,
    LLMGeneratedEntry,
    MemoryEntry,
)


_GMT8 = timezone(timedelta(hours=8))


logger = logging.getLogger(__name__)


# —— Chat Agent reason → why_want_to_save_memory 映射 ——
# ref: docs/impl-spec/memory-extract-agent-spec.md — why_want_to_save_memory 枚举
_REASON_TO_WHYSAVE: dict[str, str] = {
    "user_explicit_request": "用户明确要求记住知识点",
    "correction": "纠正事项",
    "other": "Chat Agent 判定",
}


def _now_gmt8_str() -> str:
    """GMT+8 时间戳字符串，格式 yyyy-mm-dd HH:MM:SS。

    ref: memory-extract-agent-spec.md — 字段来源约定 · timestamp
    """
    return datetime.now(_GMT8).strftime("%Y-%m-%d %H:%M:%S")


def _render_context_messages(messages) -> str:
    """把 messages 序列化为 LLM 可读的多行文本。

    按发言者与内容线性展开，便于 LLM 识别本轮对话事实。
    顺序与 MainAgent._messages 一致（不含注入的 SystemMessage）。
    """
    lines: list[str] = []
    for m in messages:
        role = getattr(m, "type", "") or m.__class__.__name__
        content = getattr(m, "content", "") or ""
        if isinstance(content, list):
            content = str(content)
        lines.append(f"[{role}] {content}")
    return "\n".join(lines)


def _intent_mode_label(intent_mode: Optional[str]) -> str:
    """ExtractInput.intent_mode -> user_intent 字符串。

    ref: memory-extract-agent-spec.md — 字段来源约定 · user_intent
    """
    if intent_mode is None:
        return "None"
    return intent_mode


_SPEC_COMPILE_TOOLS: frozenset[str] = frozenset({"vault_mcp_compile_prompt"})


async def _load_extract_spec_from_vault(lang: str) -> str:
    """通过 MCP compile_prompt 工具编译 spec/memory_extract_spec.md（含 include 展开）。

    返回编译后完整文本。
    MCP server 不可用（IndexerOfflineError）或文件缺失时向上传播异常，
    由 _run_loop 捕获后 logger.exception + 丢弃本轮。
    """
    from .mem_writer_mcp_client import mcp_vault_connection

    async with mcp_vault_connection(
        lang, wanted_tools=_SPEC_COMPILE_TOOLS
    ) as (session, _tools):
        result = await session.call_tool(
            "compile_prompt", {"path": "spec/memory_extract_spec.md"}
        )
        if result.isError:
            err_text = (
                result.content[0].text
                if result.content
                else "compile_prompt returned isError"
            )
            raise RuntimeError(
                f"compile_prompt spec/memory_extract_spec.md failed: {err_text}"
            )
        data = result.structuredContent or {}
        return data.get("content", "")


def _build_system_prompt(
    target_lang: str,
    interface_lang: str,
    channel_name: str,
    user_doc: str,
    vault_spec_content: str,
) -> str:
    """构建 Extract Agent 的 system prompt。

    vault_spec_content 来自 MCP compile_prompt 编译的 memory_extract_spec.md
    （含 memory_extract_output_spec.md / mem_entry_spec.md 等 include 展开）。
    """
    spec_doc = vault_spec_content

    # 替换占位符
    spec_doc = spec_doc.replace("{target_lang}", target_lang)

    user_doc_section = ""
    if user_doc.strip():
        user_doc_section = (
            "\n## 用户个性化偏好 (USER.md)\n"
            "以下为 USER.md 内容，用于辅助筛选判断（如判断是否'琐碎/显而易见'、"
            "'与目标学习语言相关性'、'用户偏好类应跳过'等）。\n"
            "**仅用于筛选判断**。\n\n"
            "---\n"
            f"{shift_headings(user_doc.strip(), offset=2)}\n"
            "---\n"
        )

    return spec_doc.strip() + "\n\n" + user_doc_section.rstrip()


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
        # Extract Agent 自身无状态：会话内 dedup 由 MainAgent 通过 extract 游标
        # 在输入侧完成（new/context 分离），不在此维护 headword 列表。

        # ref: 实现 · 用 langchain 的 LLM 调用 + structured output
        # ref: memory-extract-agent-spec.md — 已知简化 / 待评估
        # 抽取任务使用独立工厂 create_extract_llm()，temperature=0 以保证结构化输出确定性。
        self._llm = create_extract_llm().with_structured_output(ExtractLLMOutput)

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

    def _post_process(
        self,
        llm_entries: list[LLMGeneratedEntry],
        user_intent: str,
        new_messages_text: str = "",
        context_messages_text: str = "",
        reason: str | None = None,
    ) -> list[MemoryEntry]:
        """把 LLM 输出覆盖透传字段并补全 entry_id / timestamp / 对话消息。

        当 `reason` 不为 None 时，用 `reason` 映射值覆盖
        `why_want_to_save_memory`（Chat Agent 的触发原因为最高权威）。
        """
        ts = _now_gmt8_str()
        mapped_why = _REASON_TO_WHYSAVE.get(reason) if reason else None
        out: list[MemoryEntry] = []
        for raw in llm_entries:
            out.append(MemoryEntry(
                entry_id=str(uuid.uuid4()),
                timestamp=ts,
                chat_session_id=self._chat_session_id,
                channel_name=self._channel_name,
                user_intent=user_intent,
                lang=self._target_lang,
                interface_language=self._interface_lang,
                new_messages=new_messages_text,
                context_messages=context_messages_text,
                item_type=raw.item_type,
                why_want_to_save_memory=mapped_why or raw.why_want_to_save_memory,
                title=raw.title,
            ))
        return out

    def _extract(self, extract_input: ExtractInput) -> list[MemoryEntry]:
        """执行一次抽取，返回构造好的 MemoryEntry 列表（可能为空）。

        成功路径：返回 entries，调用方负责日志输出与转交 memory_writer。
        异常路径：调用方 _run_loop 已捕获，本函数仍允许异常向上传播。

        公开成方法是为便于测试以同步方式验证 post-process 行为。
        """
        user_doc = load_user_doc()

        vault_spec = asyncio.run(
            _load_extract_spec_from_vault(lang=self._target_lang)
        )

        system_prompt = _build_system_prompt(
            target_lang=self._target_lang,
            interface_lang=self._interface_lang,
            channel_name=self._channel_name,
            user_doc=user_doc,
            vault_spec_content=vault_spec,
        )

        intent_label = _intent_mode_label(extract_input.intent_mode)
        new_text = _render_context_messages(extract_input.new_messages)
        context_text = _render_context_messages(extract_input.context_messages)
        reason_info = f"reason: {extract_input.reason}"
        note_info = f"note: {extract_input.note}" if extract_input.note else ""
        user_msg = (
            f"intent_mode: {intent_label}\n"
            f"{reason_info}\n"
            f"{note_info}\n\n"
            f"=== 背景上下文（仅供理解对话场景，禁止从中抽取知识点）===\n"
            f"{context_text}\n\n"
            f"=== 本轮新增（唯一允许的抽取来源）===\n"
            f"{new_text}\n\n"
            "请按 system prompt 中的筛选规则与 schema 输出 JSON。"
        )

        # ref: 实现 — 用 langchain 的 LLM 调用 + structured output
        result: ExtractLLMOutput = self._llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_msg),
        ])

        entries = self._post_process(
            result.entries, intent_label, new_text, context_text,
            reason=extract_input.reason,
        )

        # ref: 日志要求 — 每个 entry info 日志输出全部字段
        for e in entries:
            logger.info(
                "memory extract entry: entry_id=%s chat_session_id=%s timestamp=%s "
                "channel_name=%s item_type=%s why=%s user_intent=%s lang=%s "
                "interface_language=%s "
                "title=%s new_messages=%r context_messages=%r",
                e.entry_id, e.chat_session_id, e.timestamp,
                e.channel_name, e.item_type, e.why_want_to_save_memory,
                e.user_intent, e.lang, e.interface_language,
                e.title, e.new_messages, e.context_messages,
            )

        # 非空才转交 writer
        if entries:
            self._memory_writer.enqueue(entries)

        return entries


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
