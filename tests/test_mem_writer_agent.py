# ref: docs/impl-spec/memory-writer-agent-spec.md
# Memory Writer Agent 核心流程与边缘测试。
# 2026-07 迁移到 Vault MCP Server：所有 fs/search 操作改为走 MCP。
# 测试用 in-memory FastMCP transport（patch mcp_vault_connection），
# 无需起 HTTP server。
#
# TEST_STYLE 要求：核心流程相关测试 + 边缘用户输入场景；
# 避免对 LLM 自然语言文本输出作字符串断言。
#
# 测试覆盖：
# - ULID 生成格式与唯一性
# - 工具沙箱：MCP server 端覆盖（test_mem_vault_mcp_server.py）
# - events 写入：stat→write/append 流程，preamble 创建、段落追加
# - system prompt：注入 mem_entry_spec + vault_spec，使用 MCP 工具名
# - MemoryWriterAgent 生命周期与异步消费
# - 单 entry 触发一次 agent.ainvoke；失败隔离
# - indexer 离线 → 丢弃 entry + logger.error
# - gateway.memory_writer 单例代理

from __future__ import annotations

import logging
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from everlingo import workspace
from everlingo.mem.agents.mem_entries import MemoryEntry
from everlingo.mem.agents.mem_writer_agent import (
    MemoryWriterAgent,
    _append_event_async,
    _build_writer_system_prompt,
    _events_rel_path,
    _format_action_event_section,
    _format_event_section,
)
from everlingo.mem.agents.mem_writer_mcp_client import (
    IndexerOfflineError,
)
from everlingo.utils.md_prompt_compiler import PackageSource, compile_prompt


# ── fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def mem_entry_spec_text():
    """从打包默认值编译真实 mem_entry_spec.md 文本，用作 _build_writer_system_prompt 的测试输入。"""
    source = PackageSource(package="everlingo.mem.vault.vault_specs.default")
    return compile_prompt("mem_entry_spec.md", source)


def _entry(
    title="gcc",
    item_type="vocab",
    why="用户明确要求记住知识点",
    lang="en",
    interface_language="zh-CN",
    timestamp="2026-11-21 14:58:56",
    chat_session_id="cs-1",
    channel_name="StdioChannel",
    user_intent="dict",
    new_messages="",
    context_messages="",
) -> MemoryEntry:
    return MemoryEntry(
        entry_id="entry-uuid-1",
        timestamp=timestamp,
        chat_session_id=chat_session_id,
        channel_name=channel_name,
        user_intent=user_intent,
        lang=lang,
        interface_language=interface_language,
        new_messages=new_messages,
        context_messages=context_messages,
        item_type=item_type,
        why_want_to_save_memory=why,
        title=title,
    )


@pytest.fixture
def tmp_vault(tmp_mcp_workspace: Path) -> Path:
    """返回 en lang vault 根（用于断言写入落盘位置）。"""
    return tmp_mcp_workspace / "memory" / "languages" / "en" / "vault"


# ── events 写入（纯函数 + MCP 流程）───────────────────────────


class TestEventsRelPath:
    def test_path_shape(self):
        e = _entry(timestamp="2026-11-21 14:58:56", lang="en")
        assert _events_rel_path(e) == "events/2026/11/2026-11-21.md"

    def test_path_handles_japanese_lang(self):
        e = _entry(timestamp="2026-11-21 14:58:56", lang="ja")
        assert _events_rel_path(e).startswith("events/2026/11/")


class TestFormatEventSection:
    def test_section_has_all_fields(self):
        e = _entry()
        section = _format_event_section(e, conversation_context="用户在查词")
        assert "## Event" in section
        assert "- chat_session_id: cs-1" in section
        assert "- entry_id: entry-uuid-1" in section
        assert "- timestamp: 2026-11-21 14:58:56" in section
        assert "- channel_name: StdioChannel" in section
        assert "- item_type: vocab" in section
        assert "- why_want_to_save_memory: 用户明确要求记住知识点" in section
        assert "- user_intent: dict" in section
        assert "- lang: en" in section
        assert "- title: gcc" in section
        assert "### mean_summary" not in section
        assert "### conversation_context" in section
        assert "用户在查词" in section

    def test_section_omits_conversation_context_when_none(self):
        """conversation_context 为 None 时省略该子段。"""
        e = _entry()
        section = _format_event_section(e, conversation_context=None)
        assert "### conversation_context" not in section


class TestAppendEvent:
    """_append_event_async 走 MCP fs 工具（stat + write/append）。"""

    def test_creates_file_with_preamble_when_missing(
        self, mcp_inmem_server, tmp_vault, caplog
    ):
        with caplog.at_level(logging.INFO, logger="everlingo"):
            with mcp_inmem_server():
                import asyncio
                asyncio.run(_append_event_async(_entry(
                    timestamp="2026-11-21 14:58:56", lang="en"
                )))
        f = tmp_vault / "events/2026/11/2026-11-21.md"
        assert f.exists()
        text = f.read_text(encoding="utf-8")
        assert text.startswith("# 当天事件")
        assert "事件按时间顺序记录" in text
        assert "事件记录格式：" in text
        assert "## Event" in text
        assert "- title: gcc" in text
        assert "### mean_summary" not in text
        assert any("events: created" in r.message for r in caplog.records)

    def test_appends_to_existing_file(
        self, mcp_inmem_server, tmp_vault, caplog
    ):
        with mcp_inmem_server():
            import asyncio
            asyncio.run(_append_event_async(_entry(
                timestamp="2026-11-21 14:58:56", lang="en"
            )))
        with caplog.at_level(logging.INFO, logger="everlingo"):
            with mcp_inmem_server():
                import asyncio
                asyncio.run(_append_event_async(_entry(
                    timestamp="2026-11-21 15:58:56",
                    lang="en",
                    title="kernel",
                )))
        f = tmp_vault / "events/2026/11/2026-11-21.md"
        text = f.read_text(encoding="utf-8")
        assert text.count("## Event") == 2
        assert "gcc" in text
        assert "kernel" in text
        assert text.count("# 当天事件") == 1
        assert any("events: appended" in r.message for r in caplog.records)


# ── action event 格式 & 写入 ──────────────────────────────────


def _create_vault_file(
    vault_root: Path,
    rel_path: str,
    title: str,
    item_type: str = "vocab",
    body: str = "# test\n\nbody content\n",
) -> Path:
    """在 vault 中创建一个知识点文件用于 delete/edit 测试。"""
    full_path = vault_root / rel_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = (
        "---\n"
        f"ulid: test123\n"
        f"slug: test\n"
        f"type: {item_type}\n"
        f"title: {title}\n"
        f"description: test\n"
        f"schema_version: 1\n"
        "---\n"
    )
    full_path.write_text(frontmatter + body, encoding="utf-8")
    return full_path


def _create_vault_file_full(
    vault_root: Path,
    rel_path: str,
    title: str,
    item_type: str = "vocab",
    body: str = "# test\n\nbody content\n",
) -> Path:
    """创建带完整保护字段的知识点文件（用于 frontmatter 编辑测试）。"""
    full_path = vault_root / rel_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = (
        "---\n"
        f"ulid: test123\n"
        f"slug: test\n"
        f"type: {item_type}\n"
        f"title: {title}\n"
        f"description: test description\n"
        f"description_in_target_lang: test\n"
        f"created_at: 2026-06-22T18:08:00+08:00\n"
        f"timestamp: 2026-06-26T09:15:00+08:00\n"
        f"schema_version: 1\n"
        f"first_seen: 2026-06-22T18:08:00+08:00\n"
        f"last_seen: 2026-06-26T09:15:00+08:00\n"
        f"seen_count: 4\n"
        "tags:\n"
        "---\n"
    )
    full_path.write_text(frontmatter + body, encoding="utf-8")
    return full_path


def _action_entry(
    operation: str = "delete",
    file_path: str = "items/vocab/test--test123.md",
    title: str = "test",
    item_type: str = "vocab",
    body: str | None = None,
    frontmatter: str | None = None,
    lang: str = "en",
    chat_session_id: str = "cs-1",
    channel_name: str = "StdioChannel",
    timestamp: str = "2026-11-21 14:58:56",
) -> MemoryEntry:
    return MemoryEntry(
        operation=operation,
        entry_id="action-uuid-1",
        timestamp=timestamp,
        chat_session_id=chat_session_id,
        channel_name=channel_name,
        user_intent="None",
        lang=lang,
        interface_language="zh-CN",
        item_type=item_type,
        title=title,
        file_path=file_path,
        body=body,
        frontmatter=frontmatter,
    )


class TestFormatActionEventSection:
    def test_delete_event_section(self):
        e = _action_entry(operation="delete")
        section = _format_action_event_section(e, "deleted")
        assert "## Event" in section
        assert "- action: deleted" in section
        assert "- title: test" in section
        assert "- file_path: items/vocab/test--test123.md" in section

    def test_edit_event_section(self):
        e = _action_entry(operation="edit", body="# new body")
        section = _format_action_event_section(e, "edited")
        assert "## Event" in section
        assert "- action: edited" in section
        assert "- title: test" in section
        assert "- file_path: items/vocab/test--test123.md" in section


class TestActionDelete:
    """_delete_entry_async 走 MCP fs 工具（stat + read + delete + events）。"""

    def test_delete_existing_file(self, mcp_inmem_server, tmp_vault):
        _create_vault_file(tmp_vault, "items/vocab/test--test123.md", title="test")
        file_path = tmp_vault / "items/vocab/test--test123.md"
        assert file_path.exists()

        with mcp_inmem_server():
            import asyncio
            agent = MemoryWriterAgent()
            entry = _action_entry(
                operation="delete",
                file_path="items/vocab/test--test123.md",
                title="test",
            )
            result = asyncio.run(agent._delete_entry_async(entry))

        assert result["ok"] is True
        assert result["file_path"] == "items/vocab/test--test123.md"
        assert result["title"] == "test"
        assert result["item_type"] == "vocab"
        assert not file_path.exists()

    def test_delete_file_not_found(self, mcp_inmem_server):
        with mcp_inmem_server():
            import asyncio
            agent = MemoryWriterAgent()
            entry = _action_entry(
                operation="delete",
                file_path="items/vocab/nonexistent--ulid.md",
            )
            result = asyncio.run(agent._delete_entry_async(entry))

        assert result["ok"] is False
        assert "file not found" in result["error"]

    def test_delete_writes_event(self, mcp_inmem_server, tmp_vault):
        _create_vault_file(tmp_vault, "items/vocab/test--test123.md", title="test")

        with mcp_inmem_server():
            import asyncio
            agent = MemoryWriterAgent()
            entry = _action_entry(
                operation="delete",
                file_path="items/vocab/test--test123.md",
                title="test",
                timestamp="2026-11-21 14:58:56",
            )
            asyncio.run(agent._delete_entry_async(entry))

        events_file = tmp_vault / "events/2026/11/2026-11-21.md"
        assert events_file.exists()
        text = events_file.read_text(encoding="utf-8")
        assert "- action: deleted" in text
        assert "- title: test" in text
        assert "- file_path: items/vocab/test--test123.md" in text

    def test_delete_missing_file_path(self):
        agent = MemoryWriterAgent()
        import asyncio
        entry = _action_entry(operation="delete", file_path="")
        result = asyncio.run(agent._delete_entry_async(entry))
        assert result["ok"] is False
        assert "file_path is required" in result["error"]


class TestActionEdit:
    """_edit_entry_async 走 MCP fs 工具（read + write + events）。"""

    def test_edit_preserves_frontmatter(self, mcp_inmem_server, tmp_vault):
        orig_body = "# original\n\noriginal content\n"
        _create_vault_file(
            tmp_vault, "items/vocab/test--test123.md",
            title="test", body=orig_body,
        )

        new_body = "# edited\n\nnew content\n"
        with mcp_inmem_server():
            import asyncio
            agent = MemoryWriterAgent()
            entry = _action_entry(
                operation="edit",
                file_path="items/vocab/test--test123.md",
                title="test",
                body=new_body,
            )
            result = asyncio.run(agent._edit_entry_async(entry))

        assert result["ok"] is True
        assert result["file_path"] == "items/vocab/test--test123.md"
        assert result["title"] == "test"

        file_path = tmp_vault / "items/vocab/test--test123.md"
        text = file_path.read_text(encoding="utf-8")
        # frontmatter preserved
        assert "ulid: test123" in text
        assert "title: test" in text
        assert "type: vocab" in text
        # frontmatter delimiters preserved
        assert text.startswith("---")
        # old body gone
        assert "original content" not in text
        # new body present
        assert "new content" in text

    def test_edit_no_body(self):
        agent = MemoryWriterAgent()
        import asyncio
        entry = _action_entry(operation="edit", file_path="items/vocab/test.md", body=None)
        result = asyncio.run(agent._edit_entry_async(entry))
        assert result["ok"] is False
        assert "body is required" in result["error"]

    def test_edit_file_not_found(self, mcp_inmem_server):
        with mcp_inmem_server():
            import asyncio
            agent = MemoryWriterAgent()
            entry = _action_entry(
                operation="edit",
                file_path="items/vocab/nonexistent--ulid.md",
                body="# new body",
            )
            result = asyncio.run(agent._edit_entry_async(entry))
        assert result["ok"] is False
        assert "read failed" in result["error"]

    def test_edit_writes_event(self, mcp_inmem_server, tmp_vault):
        _create_vault_file(
            tmp_vault, "items/vocab/test--test123.md",
            title="test", body="# original",
        )

        with mcp_inmem_server():
            import asyncio
            agent = MemoryWriterAgent()
            entry = _action_entry(
                operation="edit",
                file_path="items/vocab/test--test123.md",
                title="test",
                body="# edited",
                timestamp="2026-11-21 15:58:56",
            )
            asyncio.run(agent._edit_entry_async(entry))

        events_file = tmp_vault / "events/2026/11/2026-11-21.md"
        assert events_file.exists()
        text = events_file.read_text(encoding="utf-8")
        assert "- action: edited" in text
        assert "- title: test" in text
        assert "- file_path: items/vocab/test--test123.md" in text

    def test_edit_missing_file_path(self):
        agent = MemoryWriterAgent()
        import asyncio
        entry = _action_entry(
            operation="edit", file_path="", body="# new body",
        )
        result = asyncio.run(agent._edit_entry_async(entry))
        assert result["ok"] is False
        assert "file_path is required" in result["error"]

    def test_edit_merges_frontmatter_protected_fields(self, mcp_inmem_server, tmp_vault):
        """LLM 传入改过的 ulid/slug/seen_count → 实际文件中保留原值。"""
        _create_vault_file_full(
            tmp_vault, "items/vocab/test--test123.md",
            title="旧标题", body="# original",
        )

        new_body = "# edited\n"
        frontmatter_input = (
            "ulid: EVILCHANGED\n"
            "slug: malicious-slug\n"
            "type: grammar\n"
            "title: 新标题\n"
            "description: 新描述\n"
            "created_at: 2000-01-01T00:00:00+08:00\n"
            "timestamp: 2000-01-01T00:00:00+08:00\n"
            "schema_version: 99\n"
            "first_seen: 2000-01-01T00:00:00+08:00\n"
            "last_seen: 2000-01-01T00:00:00+08:00\n"
            "seen_count: 999\n"
        )
        with mcp_inmem_server():
            import asyncio
            agent = MemoryWriterAgent()
            entry = _action_entry(
                operation="edit",
                file_path="items/vocab/test--test123.md",
                title="旧标题",
                body=new_body,
                frontmatter=frontmatter_input,
            )
            result = asyncio.run(agent._edit_entry_async(entry))

        assert result["ok"] is True

        file_path = tmp_vault / "items/vocab/test--test123.md"
        text = file_path.read_text(encoding="utf-8")
        # 保护字段保留原值（yaml.safe_dump 会把 datetime T 归一化为空格）
        assert "ulid: test123" in text
        assert "slug: test" in text
        assert "type: vocab" in text   # 原文件是 vocab
        assert "created_at: 2026-06-22" in text
        assert "schema_version: 1" in text
        assert "first_seen: 2026-06-22" in text
        assert "seen_count: 4" in text
        # 可编辑字段被修改
        assert "title: 新标题" in text
        assert "description: 新描述" in text
        # 新 body
        assert text.endswith("# edited\n") or text.endswith("# edited\n\n")

    def test_edit_merges_frontmatter_editable_fields(self, mcp_inmem_server, tmp_vault):
        """title/description/tags 可被 LLC 传入的新值覆盖。"""
        _create_vault_file_full(
            tmp_vault, "items/vocab/edit-me--test.md",
            title="旧标题", body="# original",
        )

        new_body = "# edited\n"
        frontmatter_input = (
            "ulid: test123\n"
            "slug: test\n"
            "type: vocab\n"
            "title: 新标题\n"
            "description: 新描述\n"
            "description_in_target_lang: new target desc\n"
            "created_at: 2026-06-22T18:08:00+08:00\n"
            "timestamp: 2026-06-26T09:15:00+08:00\n"
            "schema_version: 1\n"
            "first_seen: 2026-06-22T18:08:00+08:00\n"
            "last_seen: 2026-06-26T09:15:00+08:00\n"
            "seen_count: 4\n"
            "tags:\n"
            "  - tag1\n"
            "  - tag2\n"
        )
        with mcp_inmem_server():
            import asyncio
            agent = MemoryWriterAgent()
            entry = _action_entry(
                operation="edit",
                file_path="items/vocab/edit-me--test.md",
                title="旧标题",
                body=new_body,
                frontmatter=frontmatter_input,
            )
            result = asyncio.run(agent._edit_entry_async(entry))

        assert result["ok"] is True
        assert result["title"] == "新标题"  # return 使用合并后的 title

        text = (tmp_vault / "items/vocab/edit-me--test.md").read_text(encoding="utf-8")
        assert "title: 新标题" in text
        assert "description: 新描述" in text
        assert "description_in_target_lang: new target desc" in text
        assert "tag1" in text
        assert "tag2" in text

    def test_edit_frontmatter_updates_event_title(self, mcp_inmem_server, tmp_vault):
        """审计事件中 title 使用合并后的新值。"""
        _create_vault_file_full(
            tmp_vault, "items/vocab/test--test123.md",
            title="旧标题", body="# original",
        )

        new_body = "# edited\n"
        frontmatter_input = (
            "title: 新标题\n"
            "description: 新描述\n"
        )
        with mcp_inmem_server():
            import asyncio
            agent = MemoryWriterAgent()
            entry = _action_entry(
                operation="edit",
                file_path="items/vocab/test--test123.md",
                title="旧标题",
                body=new_body,
                frontmatter=frontmatter_input,
                timestamp="2026-11-21 15:58:56",
            )
            asyncio.run(agent._edit_entry_async(entry))

        events_file = tmp_vault / "events/2026/11/2026-11-21.md"
        assert events_file.exists()
        text = events_file.read_text(encoding="utf-8")
        assert "- title: 新标题" in text
        assert "- file_path: items/vocab/test--test123.md" in text

    def test_edit_no_frontmatter_params_still_works(self, mcp_inmem_server, tmp_vault):
        """不传 frontmatter 参数时行为与原来一致。"""
        orig_body = "# original\n\noriginal content\n"
        _create_vault_file(
            tmp_vault, "items/vocab/test--test123.md",
            title="test", body=orig_body,
        )

        new_body = "# edited\n\nnew content\n"
        with mcp_inmem_server():
            import asyncio
            agent = MemoryWriterAgent()
            # 不传 frontmatter（None）
            entry = _action_entry(
                operation="edit",
                file_path="items/vocab/test--test123.md",
                title="test",
                body=new_body,
                frontmatter=None,
            )
            result = asyncio.run(agent._edit_entry_async(entry))

        assert result["ok"] is True
        text = (tmp_vault / "items/vocab/test--test123.md").read_text(encoding="utf-8")
        assert "ulid: test123" in text
        assert "title: test" in text
        assert "original content" not in text
        assert "new content" in text


class TestActionDaemonDispatch:
    """daemon thread _run_loop 分发 _ActionRequest。"""

    @pytest.fixture(autouse=True)
    def _patch_mem_entry_spec(self, mem_entry_spec_text):
        with patch(
            "everlingo.mem.agents.mem_writer_agent._load_mem_entry_spec_from_vault",
            new_callable=AsyncMock,
            return_value=mem_entry_spec_text,
        ):
            yield

    def test_process_action_delete(self, mcp_inmem_server, tmp_vault):
        _create_vault_file(tmp_vault, "items/vocab/test--test123.md", title="test")

        with mcp_inmem_server():
            agent = MemoryWriterAgent()
            entry = _action_entry(
                operation="delete",
                file_path="items/vocab/test--test123.md",
            )
            import asyncio
            result = asyncio.run(agent._delete_entry_async(entry))

        assert result["ok"] is True

    def test_run_loop_dispatches_action_request(self, mcp_inmem_server, tmp_vault):
        _create_vault_file(tmp_vault, "items/vocab/test--test123.md", title="test")
        file_path = tmp_vault / "items/vocab/test--test123.md"
        assert file_path.exists()

        with mcp_inmem_server():
            from everlingo.mem.agents.mem_writer_agent import _ActionRequest
            import concurrent.futures

            agent = MemoryWriterAgent()
            future = concurrent.futures.Future()
            entry = _action_entry(
                operation="delete",
                file_path="items/vocab/test--test123.md",
            )
            agent._queue.put(_ActionRequest(entry=entry, future=future))
            agent._queue.put(None)  # sentinel to stop the loop
            agent._run_loop()

        assert future.done()
        result = future.result()
        assert result["ok"] is True
        assert not file_path.exists()


# ── system prompt ──────────────────────────────────────────────


class TestWriterSystemPrompt:
    def test_includes_vault_spec_sections(self, mem_entry_spec_text):
        prompt = _build_writer_system_prompt(mem_entry_spec_text)
        assert "Memory Vault" in prompt
        assert "chat_session_id" in prompt

    def test_states_sandbox_rule(self, mem_entry_spec_text):
        prompt = _build_writer_system_prompt(mem_entry_spec_text)
        assert "相对 path" in prompt or "相对路径" in prompt

    def test_uses_mcp_tool_names(self, mem_entry_spec_text):
        """迁移后 system prompt 必须用 MCP 工具名（read/write/grep/...）。"""
        prompt = _build_writer_system_prompt(mem_entry_spec_text)
        for name in ("read(", "write(", "append(", "delete(",
                     "ls(", "find(", "grep(", "vault_mcp_gen_id("):
            assert name in prompt, f"missing tool: {name}"
        # 旧名不应再出现
        for old in (
            "mem_read_file", "mem_write_file", "mem_grep",
            "mem_search_files", "mem_list_directory",
            "mem_create_tmp_file", "mem_remove_file", "mem_append_file",
        ):
            assert old not in prompt, f"legacy tool name leaked: {old}"

    def test_states_read_write_once_constraint(self, mem_entry_spec_text):
        prompt = _build_writer_system_prompt(mem_entry_spec_text)
        assert "read" in prompt and "write" in prompt
        assert "至多 1 次" in prompt

    def test_includes_pragmatics_fallback_template(self, mem_entry_spec_text):
        prompt = _build_writer_system_prompt(mem_entry_spec_text)
        assert "pragmatics" in prompt

    def test_includes_entry_schema(self, mem_entry_spec_text):
        prompt = _build_writer_system_prompt(mem_entry_spec_text)
        assert "## 输入给你的 entry 结构" in prompt
        for field in (
            "chat_session_id", "entry_id", "timestamp", "channel_name",
            "item_type", "why_want_to_save_memory", "user_intent",
            "lang", "interface_language", "title",
            "new_messages", "context_messages",
        ):
            assert field in prompt, f"missing entry field: {field}"

    def test_entry_schema_appears_before_vault_spec(self, mem_entry_spec_text):
        prompt = _build_writer_system_prompt(mem_entry_spec_text)
        assert prompt.index("## 输入给你的 entry 结构") < prompt.index(
            "# memory vault 注意事项"
        )

    def test_injected_spec_headings_nested_under_parent(self, mem_entry_spec_text):
        prompt = _build_writer_system_prompt(mem_entry_spec_text)
        assert "### 记忆实体" in prompt
        for line in prompt.splitlines():
            stripped = line.lstrip()
            assert not stripped.startswith("# 记忆实体"), line
        assert "## 输入给你的 entry 结构" in prompt
        assert "# memory vault 注意事项" in prompt



# ── MemoryWriterAgent 流程测试 ─────────────────────────────────


class TestWriterAgentSync:
    """单 entry 触发一次 agent.ainvoke（per-entry build agent）。"""

    @pytest.fixture(autouse=True)
    def _patch_mem_entry_spec(self, mem_entry_spec_text):
        with patch(
            "everlingo.mem.agents.mem_writer_agent._load_mem_entry_spec_from_vault",
            new_callable=AsyncMock,
            return_value=mem_entry_spec_text,
        ):
            yield

    def _make_agent(self, mock_create_context):
        """构造 mock 掉 LLM agent 的 MemoryWriterAgent。
        调用方负责提供 patch 上下文（保持 create_agent 被 patch）。
        """
        mock_agent = MagicMock()
        mock_agent.ainvoke = MagicMock(
            return_value={"messages": [AIMessage(content="done")]}
        )
        mock_create_context.return_value = mock_agent
        return MemoryWriterAgent(), mock_agent

    def test_init_does_not_start_thread(self):
        with patch(
            "everlingo.mem.agents.mem_writer_agent.create_agent",
            return_value=MagicMock(),
        ):
            agent = MemoryWriterAgent()
        assert agent._thread is None

    def test_process_batch_writes_events_for_each_entry(
        self, mcp_inmem_server, tmp_vault
    ):
        with patch(
            "everlingo.mem.agents.mem_writer_agent.create_agent"
        ) as mock_create:
            agent, _ = self._make_agent(mock_create)
            with mcp_inmem_server():
                agent._process_batch([
                    _entry(timestamp="2026-11-21 14:58:56", title="gcc"),
                    _entry(timestamp="2026-11-21 15:58:56", title="kernel"),
                ])
        f = tmp_vault / "events/2026/11/2026-11-21.md"
        assert f.exists()
        text = f.read_text(encoding="utf-8")
        assert "gcc" in text
        assert "kernel" in text

    def test_process_batch_invokes_agent_once_per_entry(
        self, mcp_inmem_server
    ):
        with patch(
            "everlingo.mem.agents.mem_writer_agent.create_agent"
        ) as mock_create:
            agent, mock_agent = self._make_agent(mock_create)
            with mcp_inmem_server():
                agent._process_batch([
                    _entry(timestamp="2026-11-21 14:58:56", title="gcc"),
                    _entry(timestamp="2026-11-21 15:58:56", title="kernel"),
                    _entry(timestamp="2026-11-21 16:58:56", title="make"),
                ])
        assert mock_agent.ainvoke.call_count == 3

    def test_process_batch_passes_entry_to_agent_as_message(
        self, mcp_inmem_server
    ):
        with patch(
            "everlingo.mem.agents.mem_writer_agent.create_agent"
        ) as mock_create:
            agent, mock_agent = self._make_agent(mock_create)
            with mcp_inmem_server():
                agent._process_batch([_entry(title="gcc")])
        call_args = mock_agent.ainvoke.call_args[0][0]
        msgs = call_args["messages"]
        assert any("gcc" in m.content for m in msgs if hasattr(m, "content"))

    def test_events_failure_does_not_block_kb_item_write(
        self, mcp_inmem_server
    ):
        with patch(
            "everlingo.mem.agents.mem_writer_agent.create_agent"
        ) as mock_create:
            agent, mock_agent = self._make_agent(mock_create)
            with mcp_inmem_server():
                with patch(
                    "everlingo.mem.agents.mem_writer_agent._append_event_async",
                    side_effect=RuntimeError("disk full"),
                ):
                    agent._process_batch([_entry()])
        assert mock_agent.ainvoke.call_count == 1

    def test_kb_item_failure_does_not_break_batch(
        self, mcp_inmem_server, tmp_vault, caplog
    ):
        with patch(
            "everlingo.mem.agents.mem_writer_agent.create_agent"
        ) as mock_create:
            agent, mock_agent = self._make_agent(mock_create)
            mock_agent.ainvoke.side_effect = [
                RuntimeError("llm down"),
                {"messages": [AIMessage(content="ok")]},
            ]
            with caplog.at_level(logging.ERROR, logger="everlingo"):
                with mcp_inmem_server():
                    agent._process_batch([
                        _entry(title="gcc"),
                        _entry(title="kernel"),
                    ])
        assert mock_agent.ainvoke.call_count == 2
        text = (tmp_vault / "events/2026/11/2026-11-21.md").read_text(
            encoding="utf-8"
        )
        assert "gcc" in text
        assert "kernel" in text
        assert any(
            "kb item write failed" in r.message for r in caplog.records
        )


# ── lang 注入 + system prompt 路径约定回归 ────────────────────


class TestWriterLangSandbox:
    """回归：per-lang vault 正确性 + prompt 不带 $lang/ 前缀。"""

    @pytest.fixture(autouse=True)
    def _patch_mem_entry_spec(self, mem_entry_spec_text):
        with patch(
            "everlingo.mem.agents.mem_writer_agent._load_mem_entry_spec_from_vault",
            new_callable=AsyncMock,
            return_value=mem_entry_spec_text,
        ):
            yield

    def test_write_kb_item_uses_entry_lang(
        self, mcp_inmem_server, tmp_vault
    ):
        """mcp_vault_connection 必须用 entry.lang 调 session.configure；
        写入路径相对该 lang vault 根。"""
        # 直接在 in-memory MCP server 上验证：进入 connection 后
        # 用 session.write 写 vocab 文件，应落到 entry.lang 对应的 lang vault。
        import asyncio
        from everlingo.mem.agents import mem_writer_mcp_client

        with mcp_inmem_server() as (_state, configured_langs):
            async def go() -> None:
                async with mem_writer_mcp_client.mcp_vault_connection("en") as (
                    sess,
                    _tools,
                ):
                    await sess.call_tool(
                        "write",
                        {
                            "path": "items/vocab/ambiguous--01JTEST0001.md",
                            "content": (
                                "---\n"
                                "ulid: 01JTEST0001\n"
                                "type: vocab\n"
                                "headword: ambiguous\n"
                                "title: ambiguous 释义\n"
                                "seen_count: 1\n"
                                "---\n\n# ambiguous\n"
                            ),
                        },
                    )

            asyncio.run(go())

        # 验证：in-memory transport 已被覆写为走 workspace.url 文件路径，
        # 实际写入受限于 server 端的 AppState/workspace。
        # 这里至少验证 session.configure 用 lang="en" 调用过。
        assert configured_langs == ["en"]

    def test_write_kb_item_indexer_offline_drops_entry(
        self, mcp_inmem_server, tmp_vault, caplog
    ):
        """mcp_vault_connection 抛 IndexerOfflineError → entry 被丢弃 + 告警。"""
        from contextlib import asynccontextmanager
        from unittest.mock import patch as _patch

        with patch(
            "everlingo.mem.agents.mem_writer_agent.create_agent"
        ) as mock_create:
            mock_agent = MagicMock()
            mock_agent.ainvoke = MagicMock(
                return_value={"messages": [AIMessage(content="done")]}
            )
            mock_create.return_value = mock_agent
            agent = MemoryWriterAgent()

            @asynccontextmanager
            async def broken_connection(lang: str):
                raise IndexerOfflineError("indexer not running")
                yield  # unreachable

            with mcp_inmem_server():
                with _patch(
                    "everlingo.mem.agents.mem_writer_agent.mcp_vault_connection",
                    broken_connection,
                ):
                    with caplog.at_level(
                        logging.ERROR, logger="everlingo"
                    ):
                        agent._process_batch(
                            [_entry(title="ambiguous")]
                        )

        # ainvoke 没被调用（mcp_vault_connection 直接抛错）
        assert mock_agent.ainvoke.call_count == 0
        # 日志中至少一条 IndexerOfflineError
        offline_msgs = [
            r.message for r in caplog.records
            if "indexer offline" in r.message
        ]
        assert len(offline_msgs) >= 1
        # 没有文件被写入
        assert not (tmp_vault / "events/2026/11/2026-11-21.md").exists()

    def test_write_kb_item_system_prompt_no_lang_prefix(self, mem_entry_spec_text):
        prompt = _build_writer_system_prompt(mem_entry_spec_text)
        assert "$lang/items/" not in prompt
        assert "$lang/events/" not in prompt


# ── 异步守护线程测试 ──────────────────────────────────────────


class TestWriterAgentDaemon:

    @pytest.fixture(autouse=True)
    def _patch_mem_entry_spec(self, mem_entry_spec_text):
        with patch(
            "everlingo.mem.agents.mem_writer_agent._load_mem_entry_spec_from_vault",
            new_callable=AsyncMock,
            return_value=mem_entry_spec_text,
        ):
            yield

    def _start_agent_with_mock(self):
        """返回 (mock_create_context, agent)。
        调用方负责保持 mock_create_context 上下文存活（覆盖 agent 全生命周期）。
        """
        from contextlib import contextmanager

        @contextmanager
        def _ctx():
            with patch(
                "everlingo.mem.agents.mem_writer_agent.create_agent"
            ) as mock_create:
                yield mock_create

        return _ctx()

    def test_enqueue_does_not_block(self, mcp_inmem_server):
        with self._start_agent_with_mock() as mock_create:
            mock_agent = MagicMock()

            def slow_ainvoke(*args, **kwargs):
                time.sleep(0.3)
                return {"messages": [AIMessage(content="done")]}

            mock_agent.ainvoke = MagicMock(
                side_effect=lambda *a, **kw: slow_ainvoke(*a, **kw)
            )
            mock_create.return_value = mock_agent
            agent = MemoryWriterAgent()
            agent.start()

            with mcp_inmem_server():
                t0 = time.time()
                agent.enqueue([_entry()])
                elapsed = time.time() - t0
                assert elapsed < 0.05
                agent.stop(timeout=2.0)
    def test_run_loop_processes_enqueued_batches(
        self, mcp_inmem_server, tmp_vault
    ):
        with self._start_agent_with_mock() as mock_create:
            mock_agent = MagicMock()
            mock_agent.ainvoke = MagicMock(
                return_value={"messages": [AIMessage(content="ok")]}
            )
            mock_create.return_value = mock_agent
            agent = MemoryWriterAgent()
            agent.start()

            # patches must outlive the daemon thread's _process_batch;
            # expand the mcp_inmem_server window to cover the wait.
            with mcp_inmem_server():
                agent.enqueue([_entry(title="gcc")])

                deadline = time.time() + 2.0
                while (
                    time.time() < deadline
                    and mock_agent.ainvoke.call_count == 0
                ):
                    time.sleep(0.01)
                assert mock_agent.ainvoke.call_count == 1

            events_file = tmp_vault / "events/2026/11/2026-11-21.md"
            deadline = time.time() + 1.0
            while time.time() < deadline and not events_file.exists():
                time.sleep(0.01)
            assert events_file.exists()

            agent.stop()

    def test_run_loop_survives_exception_and_continues(
        self, mcp_inmem_server, caplog
    ):
        with self._start_agent_with_mock() as mock_create:
            mock_agent = MagicMock()
            first_called = MagicMock()

            def first_ainvoke(*args, **kwargs):
                first_called()
                raise RuntimeError("boom")

            mock_agent.ainvoke = MagicMock(side_effect=first_ainvoke)
            mock_create.return_value = mock_agent
            agent = MemoryWriterAgent()
            agent.start()

            with mcp_inmem_server():
                agent.enqueue([_entry(title="a")])

                deadline = time.time() + 2.0
                while time.time() < deadline and not first_called.called:
                    time.sleep(0.01)
                assert first_called.called

            mock_agent.ainvoke = MagicMock(
                return_value={"messages": [AIMessage(content="ok")]}
            )
            with mcp_inmem_server():
                with caplog.at_level(logging.ERROR, logger="everlingo"):
                    agent.enqueue([_entry(title="b")])

                    deadline = time.time() + 2.0
                    while (
                        time.time() < deadline
                        and mock_agent.ainvoke.call_count == 0
                    ):
                        time.sleep(0.01)
                    assert mock_agent.ainvoke.call_count == 1

            assert any(
                "kb item write failed" in r.message for r in caplog.records
            )
            agent.stop()

    def test_start_is_idempotent(self):
        with self._start_agent_with_mock() as mock_create:
            mock_create.return_value = MagicMock()
            agent = MemoryWriterAgent()
            agent.start()
            t1 = agent._thread
            agent.start()
            assert agent._thread is t1
            agent.stop()


# ── gateway.memory_writer 单例代理 ─────────────────────────────


class TestGatewayMemoryWriterProxy:

    @pytest.fixture(autouse=True)
    def _patch_mem_entry_spec(self, mem_entry_spec_text):
        with patch(
            "everlingo.mem.agents.mem_writer_agent._load_mem_entry_spec_from_vault",
            new_callable=AsyncMock,
            return_value=mem_entry_spec_text,
        ):
            yield

    def test_enqueue_lazily_constructs_and_starts_agent(
        self, mcp_inmem_server
    ):
        from everlingo.gateway import gateway as gw_mod

        with patch(
            "everlingo.mem.agents.mem_writer_agent.create_agent",
            return_value=MagicMock(),
        ):
            with mcp_inmem_server():
                gw_mod.memory_writer.enqueue([_entry()])

        # 触发构造后，代理持有 agent
        assert gw_mod.memory_writer._agent is not None  # type: ignore[attr-defined]
        # 守护线程已启动
        assert (
            gw_mod.memory_writer._agent._thread is not None  # type: ignore[attr-defined]
        )
        # 清理
        try:
            gw_mod.memory_writer._agent.stop()  # type: ignore[attr-defined]
        except Exception:
            pass
        gw_mod.memory_writer._agent = None  # type: ignore[attr-defined]
