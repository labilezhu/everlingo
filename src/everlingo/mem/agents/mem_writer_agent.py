# ref: docs/impl-spec/memory-writer-agent-spec.md
# Chat Agent -> Memory Extract Agent -> Memory Writer Agent 数据流水线中的"异步写 vault"。
# 全局单例：模块级实例位于 gateway.gateway.memory_writer。
# 独立 daemon Thread + queue.Queue：因单线程顺序消费，没有并发写文件问题。
# 队列内容不持久化，可接受进程非法结束导致的丢失（与 Extract Agent 一致）。
#
# ── 改造说明（2026-07 起：迁移到 Vault MCP Server）──
# 原 mem_* 工具已全部删除。所有 fs/search 操作改走 Vault MCP Server
# （由 indexer 进程内嵌的 FastMCP Streamable HTTP server 提供）。
# 客户端适配见 mem_writer_mcp_client.py：
#   - mcp_vault_connection(lang): per-entry 异步上下文，yield (session, tools)
#   - vault_mcp_gen_id: ULID 生成工具（MCP server gen_id 工具经前缀加载）
# 写入由 indexer 的 watcher 自动重新索引，无需手动 index_file。

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
from datetime import datetime
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from ...gateway.session_events import NoticeSink
from ...llm import create_agent, create_mem_writer_llm
from ...utils.md_prompt_compiler import shift_headings
from .mem_entries import MemoryEntry
from .mem_writer_mcp_client import IndexerOfflineError, mcp_vault_connection

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


_SPEC_COMPILE_TOOLS: frozenset[str] = frozenset({"vault_mcp_compile_prompt"})


async def _load_mem_entry_spec_from_vault(lang: str) -> str:
    """通过 MCP compile_prompt 工具编译 spec/mem_entry_spec.md（含 include 展开）。

    返回编译后完整文本。
    MCP server 不可用（IndexerOfflineError）或文件缺失时向上传播异常，
    由 _process_batch 捕获后丢弃该 entry。
    """
    from .mem_writer_mcp_client import mcp_vault_connection

    async with mcp_vault_connection(
        lang, wanted_tools=_SPEC_COMPILE_TOOLS
    ) as (session, _tools):
        result = await session.call_tool(
            "compile_prompt", {"path": "spec/mem_entry_spec.md"}
        )
        if result.isError:
            err_text = (
                result.content[0].text
                if result.content
                else "compile_prompt returned isError"
            )
            raise RuntimeError(
                f"compile_prompt spec/mem_entry_spec.md failed: {err_text}"
            )
        data = result.structuredContent or {}
        return data.get("content", "")


def _build_writer_system_prompt(mem_entry_spec_content: str) -> str:
    """构建 Memory Writer Agent 的 system prompt。

    ref: docs/impl-spec/memory-writer-agent-spec.md — System prompt
    mem_entry_spec.md 已通过 MCP compile_prompt 工具从 vault 加载并展开
    include 指令，作为参数传入。此处对其 shift_headings(+2) 使其最浅
    标题 h1 → h3，嵌套于外层 `## 输入给你的 entry 结构` (h2) 之下。
    与 chat-agent-spec.md「*.md 注入需降级标题」约定一致。

    工具名约定：使用 Vault MCP Server 暴露的 fs 工具
    原名（`vault_mcp_read` / `vault_mcp_write` / `vault_mcp_search` / ...）+ Utility 工具 `vault_mcp_gen_id`。
    """
    input_entry_spec_doc = shift_headings(
        mem_entry_spec_content,
        offset=2,
    )

    prefix = """你是 EverLingo 的 Memory Writer Agent。Memory Extract Agent 会把筛选出的
conversation memory entries 异步转交给你，由你把每个 entry 合并或写入 memory vault。
你**不**与用户对话。你**不**接受外部输入（除 Extract Agent 转交的 entry 外）。

## 基本概念
Everlingo: 一个有记忆的 AI 语言学习帮手。可以回答用户语言学习问题，并在用户要求下记录笔记。你是它的一个运行期实例组件。
Memory vault : 可简称为 vault 。 Everlingo 个人语言学习笔记库，以语言知识点 markdown 文件组成的，有规范目录结构和文件结构组成的目录。一个每个 Memory vault 只保存一种指定的 `目标学习语言` 的知识。 用户可以有多个 `目标学习语言`，但每种 `目标学习语言` 只能有一个 Memory vault。 即 `目标学习语言` 和 Memory vault 是一对一的关系。

### 语言配置

每次处理的 entry 携带两个语言相关字段：

- `目标学习语言`：来源于 entry 的 `lang` 字段（语言代码，如 `ja`、`en`）。 下文引用为 $lang
- `界面语言`：来源于 entry 的 `interface_language` 字段（语言代码，如 `zh-CN`）。

两者的值均由 Memory Extract Agent 在上游填充，你直接采用 entry 中的值，
不要自行推断或改写。


## 输入给你的 entry 结构

每轮你会收到**一个** entry（JSON 格式），其完整结构与字段含义如下。
下文为该 schema 的规范说明，请严格按字段含义理解 entry 内容。

---

"""
    suffix = """


---

# memory vault 注意事项

## 目录分工

events/ 目录由代码直接追加，不由你处理；你只负责 items/ 知识库条目的写入。

注意：所有写入 memory vault 里 markdown 文件的内容，均应该来源于 输入的 entry 信息。对于 memory vault 结构和示例文件的章节，如 entry 有对应内容就应该填上，如 entry 没有对应内容，注意不要自行生成填入。你的所有填入的信息，均应该来源于 entry。不应该自己生成信息填入。

## 写作语言

memory vault 中的 markdown 文件正文，主要语言必须使用 entry 的 `interface_language`
字段（界面语言）编写。

对 `目标学习语言`（entry 的 `lang` 字段）的引用——例如该语言的词语、例句、示例、
术语——应使用 `目标学习语言` 本身书写，不要翻译成界面语言。

## 工具说明

### 工具清单（Vault MCP Server）

你只能使用下列工具操作 memory vault：

文件操作类(fs 工具集)：
- vault_mcp_read(简称 read)
- vault_mcp_write(简称 write)
- vault_mcp_append(简称 append)
- vault_mcp_delete(简称 delete)
- vault_mcp_ls(简称 ls)
- vault_mcp_find(简称 find)
- vault_mcp_grep(简称 grep)

注意，文件操作类工具的参数 path 。均只能使用相对于 Memory Vault 的路径，如 `items/vocab` 。

Utility 工具：
- vault_mcp_gen_id(简称 gen_id)

Memory Vault 搜索类：
- vault_mcp_search(简称 search)

### 工具使用说明

search 要点：
- 默认 `mode=hybrid`（推荐，混合全文 + 语义）。
- `lang` 参数不要传
- 命中结果的 `file_path` 相对当前 vault 根，可直接喂给 `read` / `write` 等 fs 工具集。

vault 目录结构规范和各类文件格式说明：
可以调用 read(path="spec/vault_spec.md") 工具，返回的 content 为 vault 目录结构规范和各类文件格式说明。调用 search / fs 工具集 前，先学习规范和 vault 的知识。

spec/vault_spec.md 文件链接到其它子规范 md 文件，请按需要读取。

典型用法： `read(path="spec/vault_spec.md")` → `search(q="...", mode="hybrid")` → `read(path=<hit.file_path>)` → `write(path=..., content=...)`。

### 工具的沙箱规则（强制）
所有 fs 工具集**只能使用相对 path**，相对于 Memory Vault 的路径。
工具层会强制校验：解析后的绝对路径不能逃出该 lang 的 vault_dir，
否则直接报错。
这意味着：
- 不允许使用绝对路径（如 `/etc/passwd`）。
- 不允许使用 `..` 跳出（如 `../foo`）。

### 工具调用约束

- 对**目标 markdown 文件**：`read` 至多 1 次、`write` 至多 1 次。
- `vault_mcp_gen_id` 仅在新建条目时调用 1 次。
- 不要创建 `tmp/` 下的临时文件（除非确有需要）

## 生成 conversation_context

entry 中的 `new_messages` 和 `context_messages` 字段包含了触发本次记忆的原始对话内容。
在将 entry 写入 kb 条目时，你需要根据对话内容生成 `conversation_context`（一两句话，
描述用户在什么场景下查询/学习这个知识点，使用界面语言）。
`conversation_context` 需要写入两个位置：

1. kb 条目 markdown 文件的 `## 遇到记录` 节中描述本次遇到场景。
2. 写入确认 JSON 的 `conversation_context` 字段。

## 写入完成确认

完成所有文件写入后，你的**最终回复**（最后一条 AIMessage）必须是一个 JSON 对象，
格式如下：

```json
{
  "updated_files": ["items/vocab/ufo.md"],
  "update_summary": "简要描述本次更新内容，如：新建词条 ufo，含释义与例句",
  "conversation_context": "用户在学习日语小说《罗生门》时直接查词"
}
```

- `updated_files`：本次写入/修改的所有 vault 文件相对路径列表
- `update_summary`：一句话概述更新内容，使用 entry 的 interface_language
- `conversation_context`：根据 entry 的 new_messages 和 context_messages 字段生成的对话场景描述

不要在此回复中输出其他内容。若写入失败无需此确认，回复空内容即可。

## 单个 entry 处理流程

每次你会收到**一个** entry（JSON 格式），按下列步骤处理：

1. **search 是否已有该条目**。 在 search 返回的结果中作判断，如果信息片段不足，用 read 加载文件分析。
2. **如果已有该条目文件**：
    1. `read(file_path)` 读取一次（**整轮不超过一次**）。
    2. 按 memory vault 结构要求，在内存中合并 entry 的内容到条目文件。
    3. `write(file_path, new_content)` 写入。
3. **如果未命中**（新建条目）：
     1. `vault_mcp_gen_id()` 取一个 ULID（26 字符）作为 frontmatter `ulid` 与文件名 ulid 部分。
    2. 按 memory vault 结构要求，构造 slug。
    3. 文件名按 memory vault 结构要求。
    4. 按 memory vault 结构 中对应 type 的模板构造 frontmatter + 正文。
    5. `write(file_path, content)` 创建并写入文件。

如需在 `tmp/` 目录下创建临时文件（例如先写一个临时草稿再合并），用
`write(path="tmp/tmp_<vault_mcp_gen_id()>.md", content="...")`；但通常
直接写目标文件即可，不需要 tmp 步骤。


"""
    return (
        prefix
        + input_entry_spec_doc.strip()
        + suffix
    )


# ── events/ 写入（纯代码，无 LLM；走 MCP）─────────────────────────


def _events_rel_path(entry: MemoryEntry) -> str:
    """构造当日 events 文件相对 path: events/<YYYY>/<MM>/<YYYY-MM-DD>.md."""
    dt = datetime.strptime(entry.timestamp, _TIMESTAMP_FMT)
    return (
        f"events/"
        f"{dt.year:04d}/{dt.month:02d}/"
        f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}.md"
    )


def _format_event_section(
    entry: MemoryEntry,
    conversation_context: str | None = None,
) -> str:
    """按 events_spec.md 段落格式构造一个 event markdown 段落。

    ref: events_spec.md — 每个 event 是一个 ## Event 段落，包含字段列表
    与 conversation_context 子段。
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
        ("title", entry.title),
    ]
    field_lines = "\n".join(f"- {name}: {value}" for name, value in fields)

    parts = [f"## Event\n{field_lines}\n"]

    if conversation_context:
        parts.append(
            f"\n### conversation_context\n{conversation_context}\n"
        )

    return "".join(parts)


async def _append_event_async(
    entry: MemoryEntry,
    conversation_context: str | None = None,
) -> None:
    """把单条 entry 追加到当日 events 文件（通过 MCP fs 工具）。

    ref: memory-writer-agent-spec.md — 记录 events 的实现
    events/ 追加不该走 LLM：按日期拼路径，通过 MCP `stat` 判断文件
    是否存在 → 不存在则 `write` 写「文件前置内容」，存在则
    `append` 追加 `## Event` 段落。
    conversation_context 由 Writer LLM 在 kb item 写入时生成后传回。

    MCP 写入由 indexer watcher 自动入索引；不再走 gateway 侧的
    `SearchClient.index_file` 钩子（钩子链路已删除）。
    """
    rel = _events_rel_path(entry)
    section = _format_event_section(entry, conversation_context)

    async with mcp_vault_connection(entry.lang) as (session, _tools):
        stat_result = await session.call_tool("stat", {"path": rel})
        if stat_result.isError:
            raise RuntimeError(
                f"events stat failed: {stat_result.content[0].text}"
            )
        exists = bool(
            (stat_result.structuredContent or {}).get("exists", False)
        )

        if not exists:
            write_result = await session.call_tool(
                "write", {"path": rel, "content": _EVENT_FILE_PREAMBLE}
            )
            if write_result.isError:
                raise RuntimeError(
                    f"events write preamble failed: "
                    f"{write_result.content[0].text}"
                )
            action = "created"
        else:
            action = "appended"

        append_result = await session.call_tool(
            "append", {"path": rel, "content": section + "\n"}
        )
        if append_result.isError:
            raise RuntimeError(
                f"events append failed: {append_result.content[0].text}"
            )

    logger.info(
        "events: %s %s/%s, content=%s",
        action, entry.lang, rel, section,
    )


# ── kb item 写入（LLM 驱动）──────────────────────────────────────────


def _render_entry_payload(entry: MemoryEntry) -> str:
    """把 MemoryEntry 序列化为 LLM 可读的 JSON 文本块。"""
    return json.dumps(entry.model_dump(), ensure_ascii=False, indent=2)


def _parse_write_confirmation(
    messages: list,
) -> tuple[list[str] | None, str | None, str | None]:
    """从 Writer agent 最终 AIMessage 解析写入确认 JSON。

    Writer LLM 在完成写入后应在最终 AIMessage 输出如下 JSON：
    {"updated_files": [...], "update_summary": "...", "conversation_context": "..."}

    Returns:
        (updated_files, update_summary, conversation_context) on success,
        (None, None, None) on failure.
    """
    import json
    import re

    for msg in reversed(messages):
        if not hasattr(msg, "content") or not msg.content:
            continue
        content = msg.content.strip()

        # Try fenced JSON block first
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
        if m:
            try:
                data = json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
            files = data.get("updated_files")
            summary = data.get("update_summary")
            conv_ctx = data.get("conversation_context")
            if isinstance(files, list) and isinstance(summary, str):
                return files, summary, conv_ctx if isinstance(conv_ctx, str) else None

        # Try plain JSON object in content
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            continue
        files = data.get("updated_files")
        summary = data.get("update_summary")
        conv_ctx = data.get("conversation_context")
        if isinstance(files, list) and isinstance(summary, str):
            return files, summary, conv_ctx if isinstance(conv_ctx, str) else None

        # Only inspect the final AIMessage
        break

    return None, None, None


# ── 主类 ──────────────────────────────────────────────────────────────


class MemoryWriterAgent:
    """Memory Writer Agent，异步守护线程 + queue.Queue 消费 entries。

    ref: docs/impl-spec/memory-writer-agent-spec.md

    - 全局单例（位于 gateway.gateway.memory_writer 模块级）。
    - `enqueue(entries)` 仅入队、不阻塞，由 Extract Agent 调用。
    - daemon 线程顺序消费 entries 列表，先写 events（代码），再写 kb item（LLM）。
    - 单线程顺序执行 → 没有并发写文件问题。
    - 所有 fs/search 操作走 Vault MCP Server（per-entry stream）。
      indexer 离线 → 丢弃 entry + logger.error 告警（不重试、不阻塞队列）。
    """

    def __init__(self, notice_sink: NoticeSink | None = None) -> None:
        self._queue: "queue.Queue[Optional[list[MemoryEntry]]]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None

        # ref: memory-writer-agent-spec.md — 用 langchain 的 agent 框架
        # LLM 工厂使用 create_mem_writer_llm()（temperature=0），
        # kb items 正文（释义/例句/记忆钩子）需要自然语言写作。
        # 工具集 per-entry 重建（依赖 mcp_vault_connection session）。
        # system prompt 也 per-entry 重建（mem_entry_spec 从 vault 加载）。
        self._llm = create_mem_writer_llm()
        self._notice_sink = notice_sink

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
        """对一批 entries 顺序执行：先 kb item（LLM）→ 后 events（代码）。

        ref: memory-writer-agent-spec.md — 处理 conversation memory entries
        conversation_context 由 Writer LLM 在 kb item 写入时生成，
        通过 LLM 确认 JSON 传回，用于 events 记录。
        indexer 离线（IndexerOfflineError）→ 丢弃该 entry + logger.error ，
        不阻塞队列继续消费后续 entry。
        """
        for entry in entries:
            # 1. kb item 写入：LLM 生成 conversation_context
            conv_ctx: str | None = None
            try:
                conv_ctx = asyncio.run(self._write_kb_item_async(entry))
            except IndexerOfflineError as e:
                logger.error(
                    "kb item write dropped (indexer offline): entry_id=%s "
                    "title=%s err=%s",
                    entry.entry_id, entry.title, e,
                )
            except Exception:
                logger.exception(
                    "kb item write failed for entry_id=%s title=%s",
                    entry.entry_id, entry.title,
                )

            # 2. events 追加：纯代码，无 LLM
            try:
                asyncio.run(_append_event_async(entry, conv_ctx))
            except IndexerOfflineError as e:
                logger.error(
                    "events append dropped (indexer offline): entry_id=%s "
                    "title=%s err=%s",
                    entry.entry_id, entry.title, e,
                )
            except Exception:
                logger.exception(
                    "events append failed for entry_id=%s title=%s",
                    entry.entry_id, entry.title,
                )

    async def _write_kb_item_async(self, entry: MemoryEntry) -> str | None:
        """对单个 entry 调一次 LLM agent，返回 conversation_context（可能为 None）。

        ref: memory-writer-agent-spec.md — 更新知识点类 memory items
        先通过 MCP compile_prompt 从 vault 加载 mem_entry_spec.md 构建 system
        prompt；再 per-entry 打开一条 MCP stream 加载过滤后的 fs 工具 +
        vault_mcp_gen_id 工具，构建 langchain agent，调 ainvoke。
        spec 加载失败（IndexerOfflineError）向上传播，调用方丢弃该 entry。
        若通知 sink 已注入，写成功后将写入确认发给对应 Session。
        返回 conversation_context（由 LLM 在确认 JSON 中输出）。
        """
        spec_content = await _load_mem_entry_spec_from_vault(entry.lang)
        system_prompt = _build_writer_system_prompt(spec_content)

        payload = _render_entry_payload(entry)
        user_msg = (
            "请将以下 entry 合并或写入 memory vault。\n\n"
            f"```json\n{payload}```"
        )
        async with mcp_vault_connection(entry.lang) as (_session, tools):
            agent = create_agent(
                self._llm,
                tools=tools,
                system_prompt=system_prompt,
            )
            response = await agent.ainvoke({
                "messages": [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_msg),
                ]
            })

        # ── 解析写入确认并通知对应 Session ─────────────────
        files, summary, conv_ctx = _parse_write_confirmation(response["messages"])
        if files is not None and self._notice_sink is not None:
            self._notice_sink.notify(
                session_id=entry.chat_session_id,
                source="memory_writer",
                updated_files=files,
                update_summary=summary or "",
                title=entry.title,
                lang=entry.lang,
            )
            logger.info(
                "notified session %s: written %s, files=%s, summary=%s",
                entry.chat_session_id, entry.title, files, summary,
            )
        elif files is None and self._notice_sink is not None:
            logger.warning(
                "writer did not emit confirmation for entry_id=%s title=%s",
                entry.entry_id, entry.title,
            )

        return conv_ctx
