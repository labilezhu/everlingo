# ref: docs/impl-spec/memory-writer-agent-spec.md
# Chat Agent -> Memory Extract Agent -> Memory Writer Agent 数据流水线中的"异步写 vault"。
# 全局单例：模块级实例位于 gateway.gateway.memory_writer。
# 独立 daemon Thread + queue.Queue：因单线程顺序消费，没有并发写文件问题。
# 队列内容不持久化，可接受进程非法结束导致的丢失（与 Extract Agent 一致）。

from __future__ import annotations

import json
import logging
import queue
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from ... import workspace
from ...llm import create_agent, create_mem_writer_llm
from ...utils.md_prompt_compiler import PackageSource, compile_prompt, shift_headings
from .mem_entries import MemoryEntry
from .mem_writer_tools import build_mem_writer_tools, set_current_lang

logger = logging.getLogger(__name__)


# ── 常量 ──────────────────────────────────────────────────────────────


# ref: memory-extract-agent-spec.md — entry.timestamp 格式
_TIMESTAMP_FMT = "%Y-%m-%d %H:%M:%S"

# ref: events_spec.md — 当日 events 文件首次创建时写入的「文件前置内容」。
# 见 events_spec.md:24-32
_EVENT_FILE_PREAMBLE = (
    "# 当天事件\n\n"
    "事件按时间顺序记录，即最早的事件在前面。\n"
    "事件记录格式：\n\n"
)


# ── 系统提示词构建 ──────────────────────────────────────────────────


def _build_writer_system_prompt() -> str:
    """构建 Memory Writer Agent 的 system prompt。

    ref: docs/impl-spec/memory-writer-agent-spec.md — System prompt
    通过 PackageSource + compile_prompt 编译 mem_entry_spec.md 与 vault_spec.md，
    自动展开 vault_spec.md 内嵌的 {{ include kb_items_spec.md }} 与
    {{ include events_spec.md }}。mem_entry_spec.md 用于告知 LLM 其输入 entry
    的完整字段结构与含义。

    注入前对两份 spec 文档整体 shift_headings(+2)，使其最浅标题 h1 → h3，
    嵌套于外层 `## 输入 entry 结构` / `## memory vault 结构` (h2) 之下。
    与 chat-agent-spec.md「*.md 注入需降级标题」约定一致。
    """
    entry_spec_doc = shift_headings(
        compile_prompt(
            "mem_entry_spec.md",
            PackageSource(package="everlingo.mem.agents"),
        ),
        offset=2,
    )
    vault_doc = shift_headings(
        compile_prompt(
            "vault_spec.md",
            PackageSource(package="everlingo.mem.vault"),
        ),
        offset=2,
    )

    prefix = """你是 EverLingo 的 Memory Writer Agent。Memory Extract Agent 会把筛选出的
conversation memory entries 异步转交给你，由你把每个 entry 合并或写入 memory vault。
你**不**与用户对话。你**不**接受外部输入（除 Extract Agent 转交的 entry 外）。

## 语言配置

每次处理的 entry 携带两个语言相关字段：

- `目标学习语言`：来源于 entry 的 `lang` 字段（语言代码，如 `ja`、`en`）。 下文引用为 $lang
- `界面语言`：来源于 entry 的 `interface_language` 字段（语言代码，如 `zh-CN`）。

两者的值均由 Memory Extract Agent 在上游填充，你直接采用 entry 中的值，
不要自行推断或改写。


## 输入 entry 结构

每轮你会收到**一个** entry（JSON 格式），其完整结构与字段含义如下。
下文为该 schema 的规范说明，请严格按字段含义理解 entry 内容。

---

"""
    middle = """


## memory vault 结构

下文为 vault 的结构规范，请严格遵守其中的目录布局、文件命名、frontmatter 字段、
知识库条目正文模板。

---

"""
    suffix = """

---

# memory vault 注意事项

events/ 目录由代码直接追加，不由你处理；你只负责 items/ 知识库条目的写入。
（sandbox 根已按 entry 的 `lang` 解析到该语言的 vault
$workspace/memory/languages/$lang/vault/，路径中**不要**再带 $lang/ 前缀。）

注意：所有写入 memory vault 里 markdown 文件的内容，均应该来源于 输入的 entry 信息。对于 memory vault 结构和示例文件的章节，如 entry 有对应内容就应该填上，如 entry 没有对应内容，注意不要自行生成填入。你的所有填入的信息，均应该来源于 entry。不应该自己生成信息填入。

## 写作语言

memory vault 中的 markdown 文件正文，主要语言必须使用 entry 的 `interface_language`
字段（界面语言）编写。

对 `目标学习语言`（entry 的 `lang` 字段）的引用——例如该语言的词语、例句、示例、
术语——应使用 `目标学习语言` 本身书写，不要翻译成界面语言。

## 工具的沙箱规则（强制）
所有 mem_* 工具**只能使用相对 path**，相对于
`$workspace/memory/languages/$lang/vault/`（`$lang` 为 entry 的 `lang`
字段对应的目标学习语言目录，由工具层按当前会话的 `lang` 自动解析）。
工具层会强制校验：解析后的绝对路径不能逃出该 lang 的 vault_dir，
否则直接报错。
这意味着：
- 不允许使用绝对路径（如 `/etc/passwd`）。
- 不允许使用 `..` 跳出（如 `../foo`）。
- 不需要写 `memory/languages/$lang/vault/` 前缀（路径默认就在
  lang vault 根之下），也**不要**再写 `$lang/` 前缀。

## 单个 entry 处理流程

每次你会收到**一个** entry（JSON 格式），按下列步骤处理：

1. **定位 items 目录**：`items/<item_type>/`（如 `items/vocab/`）。
   **不要**在路径前加 `$lang/`（sandbox 根已经是 lang vault）。
2. **查找是否已有该 headword 的条目**：用 `mem_grep` 在上述目录递归搜索
   headword 文本。`mem_grep` 返回 `[{file_path, matched_text}]`。
3. **如果命中**（条目已存在）：
   1. `mem_read_file(file_path)` 读取一次（**整轮不超过一次**）。
   2. 在内存中合并：
      - 在文件末尾的「## 遇到记录」追加新一行（格式：`- <YYYY-MM-DD>：<conversation_context>`）。
      - 更新 frontmatter：`last_seen` = 本次 timestamp（ISO 8601 GMT+8）；
         `seen_count` += 1；`timestamp` = 当前时间。
      - 必要时根据 kb_items_spec 中对应 item_type 的模板补充正文内容
        （例如新发现的相关用法 / 常见错误等）。
   3. `mem_write_file(file_path, new_content)` 写入一次（**整轮不超过一次**）。
4. **如果未命中**（新建条目）：
   1. `mem_gen_id()` 取一个 ULID（26 字符）作为 frontmatter `id` 与文件名 ulid 部分。
   2. 构造 main_file_name：从 headword 派生，去掉 url/操作系统不安全字符，
      空格替换为下划线。例如 `曖昧` → `曖昧`、`take for granted` → `take_for_granted`。
   3. 文件名 = `{main_file_name}--{ulid}.md`。
   4. 按 kb_items_spec 中对应 item_type 的模板构造 frontmatter + 正文。
         `first_seen` / `last_seen` / `created_at` / `timestamp` 都用本次 timestamp（ISO 8601 GMT+8）。
      `seen_count` = 1。
   5. `mem_write_file(file_path, content)` 创建并写入文件。

## 工具调用约束

- 对**目标 markdown 文件**：`mem_read_file` 至多 1 次、`mem_write_file` 至多 1 次。
- `mem_grep` 用于查找，可调用多次直到定位目标。
- `mem_gen_id` 仅在新建条目时调用 1 次。
- 不要创建 `tmp/` 下的临时文件（除非确有需要）；最终结果直接写入目标 kb item 文件。


## 日志

你不需要主动写日志；工具层会自动记录每次写入的文件路径与内容。
"""
    return (
        prefix
        + entry_spec_doc.strip()
        + middle
        + vault_doc.strip()
        + suffix
    )


# ── events/ 写入（纯代码，无 LLM）──────────────────────────────────


def _events_rel_path(entry: MemoryEntry) -> str:
    """构造当日 events 文件相对 path: events/<YYYY>/<MM>/<YYYY-MM-DD>.md."""
    dt = datetime.strptime(entry.timestamp, _TIMESTAMP_FMT)
    return (
        f"events/"
        f"{dt.year:04d}/{dt.month:02d}/"
        f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}.md"
    )


def _format_event_section(entry: MemoryEntry) -> str:
    """按 events_spec.md 段落格式构造一个 event markdown 段落。

    ref: events_spec.md:34-54 — 每个 event 是一个 ## Event 段落，包含字段列表
    与 mean_summary / conversation_context 两个 ### 子段。
    """
    fields = [
        ("chat_session_id", entry.chat_session_id),
        ("entry_id", entry.entry_id),
        ("timestamp", entry.timestamp),
        ("channel_name", entry.channel_name),
        ("item_type", entry.item_type),
        ("why_want_to_save_memory", entry.why_want_to_save_memory),
        ("user_intent", entry.user_intent),
        ("lang", entry.lang),
        ("headword", entry.headword),
    ]
    field_lines = "\n".join(f"- {name}: {value}" for name, value in fields)
    return (
        f"## Event\n"
        f"{field_lines}\n"
        f"\n"
        f"### mean_summary\n"
        f"{entry.mean_summary}\n"
        f"\n"
        f"### conversation_context\n"
        f"{entry.conversation_context}\n"
    )


def _append_event(entry: MemoryEntry) -> None:
    """把单条 entry 追加到当日 events 文件。

    ref: memory-writer-agent-spec.md — 记录 events 的实现
    events/ 追加不该走 LLM：按日期拼路径，文件不存在则创建带「文件前置内容」
    的 markdown 文件，否则按 events_spec.md:34-54 追加一个 ## Event 段落。

    ref: docs/impl-spec/search/memory-vault-search-spec.md — Writer 集成
    写后通过 mem_writer_tools 注入的钩子触发 SearchClient.index_file(lang, path)，
    让 indexer 即时拿到新追加的 event 段。失败时静默吞掉（fire-and-forget）。
    """
    rel = _events_rel_path(entry)
    abs_path = (workspace.lang_vault_dir(entry.lang) / rel).resolve()
    abs_path.parent.mkdir(parents=True, exist_ok=True)

    created = False
    if not abs_path.exists():
        abs_path.write_text(_EVENT_FILE_PREAMBLE, encoding="utf-8")
        created = True

    section = _format_event_section(entry)
    with abs_path.open("a", encoding="utf-8") as f:
        f.write(section + "\n")

    logger.info(
        "events: %s %s, content=%s",
        "created" if created else "appended",
        rel,
        section,
    )
    # 触发索引钩子
    from .mem_writer_tools import _fire_post_write

    _fire_post_write(entry.lang, rel, "index")


# ── kb item 写入（LLM 驱动）──────────────────────────────────────────


def _render_entry_payload(entry: MemoryEntry) -> str:
    """把 MemoryEntry 序列化为 LLM 可读的 JSON 文本块。"""
    return json.dumps(entry.model_dump(), ensure_ascii=False, indent=2)


# ── 主类 ──────────────────────────────────────────────────────────────


class MemoryWriterAgent:
    """Memory Writer Agent，异步守护线程 + queue.Queue 消费 entries。

    ref: docs/impl-spec/memory-writer-agent-spec.md

    - 全局单例（位于 gateway.gateway.memory_writer 模块级）。
    - `enqueue(entries)` 仅入队、不阻塞，由 Extract Agent 调用。
    - daemon 线程顺序消费 entries 列表，先写 events（代码），再写 kb item（LLM）。
    - 单线程顺序执行 → 没有并发写文件问题。
    """

    def __init__(self) -> None:
        self._queue: "queue.Queue[Optional[list[MemoryEntry]]]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None

        # ref: memory-writer-agent-spec.md — 用 langchain 的 agent 框架
        # LLM 工厂使用 create_mem_writer_llm()（temperature=0），kb items 正文（释义/例句/
        # 记忆钩子）需要自然语言写作。文件结构操作靠 system prompt 约束 + 工具沙箱保证。
        self._tools = build_mem_writer_tools()
        self._system_prompt = _build_writer_system_prompt()
        self._agent = create_agent(
            create_mem_writer_llm(),
            tools=self._tools,
            system_prompt=self._system_prompt,
        )

    # ── 生命周期 ────────────────────────────────────────────────

    def start(self) -> None:
        """启动守护消费线程。已 alive 时幂等。"""
        if self._thread is not None and self._thread.is_alive():
            return
        # daemon=True：进程退出时直接丢弃未处理项，与 spec「可接受丢失」一致
        self._thread = threading.Thread(
            target=self._run_loop,
            name="mem-writer",
            daemon=True,
        )
        self._thread.start()

    def enqueue(self, entries: list[MemoryEntry]) -> None:
        """入队即返回，不阻塞。

        ref: memory-extract-agent-spec.md — 异步执行 · Extract Agent 转交 entries
        """
        self._queue.put(list(entries))

    def stop(self, timeout: float = 5.0) -> None:
        """发送结束哨兵并等待线程退出。供测试与优雅关闭使用。"""
        self._queue.put(None)
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    # ── 主循环 ────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        """消费 entries 列表；遇 None 哨兵退出。"""
        while True:
            item = self._queue.get()
            if item is None:
                return
            try:
                self._process_batch(item)
            except Exception:
                # ref: 失败处理 —— logger.exception 后丢弃本批 entries，继续消费
                logger.exception("memory writer batch failed")

    # ── 批处理 ────────────────────────────────────────────────────

    def _process_batch(self, entries: list[MemoryEntry]) -> None:
        """对一批 entries 顺序执行：先 events（代码）→ 再 kb item（LLM）。

        ref: memory-writer-agent-spec.md — 处理 conversation memory entries
        """
        # 1. events 追加：纯代码，无 LLM
        for entry in entries:
            try:
                _append_event(entry)
            except Exception:
                logger.exception(
                    "events append failed for entry_id=%s headword=%s",
                    entry.entry_id, entry.headword,
                )

        # 2. kb item 写入：逐 entry 调一次 LLM agent
        for entry in entries:
            try:
                self._write_kb_item(entry)
            except Exception:
                logger.exception(
                    "kb item write failed for entry_id=%s headword=%s",
                    entry.entry_id, entry.headword,
                )

    def _write_kb_item(self, entry: MemoryEntry) -> None:
        """对单个 entry 调一次 LLM agent，由 LLM 通过工具完成 grep/read/write。

        ref: memory-writer-agent-spec.md — 更新知识点类 memory items
        ref: docs/impl-spec/worksplace/workspace.md — per-lang vault
        在调 agent 之前 set_current_lang(entry.lang)，让 mem_* 工具的
        sandbox 根解析到 entry 的目标学习语言 vault
        ($workspace/memory/languages/$lang/vault/)。finally 里 reset，
        避免跨 entry 状态泄漏（队列中下一条 entry 可能 lang 不同）。
        """
        set_current_lang(entry.lang)
        try:
            payload = _render_entry_payload(entry)
            user_msg = (
                "请将以下 entry 合并或写入 memory vault。\n\n"
                f"```json\n{payload}```"
            )
            self._agent.invoke({
                "messages": [
                    SystemMessage(content=self._system_prompt),
                    HumanMessage(content=user_msg),
                ]
            })
        finally:
            set_current_lang(None)