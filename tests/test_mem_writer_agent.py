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
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from everlingo import workspace
from everlingo.mem.agents.mem_entries import MemoryEntry
from everlingo.mem.agents.mem_writer_agent import (
    MemoryWriterAgent,
    _append_event_async,
    _build_writer_system_prompt,
    _events_rel_path,
    _format_event_section,
)
from everlingo.mem.agents.mem_writer_mcp_client import (
    IndexerOfflineError,
)


# ── fixtures ──────────────────────────────────────────────────────


def _entry(
    headword="gcc",
    item_type="vocab",
    why="用户明确要求记住知识点",
    lang="en",
    interface_language="zh-CN",
    timestamp="2026-11-21 14:58:56",
    chat_session_id="cs-1",
    channel_name="StdioChannel",
    user_intent="dict",
    mean="GNU C 编译器",
    ctx="用户在查词",
) -> MemoryEntry:
    return MemoryEntry(
        entry_id="entry-uuid-1",
        timestamp=timestamp,
        chat_session_id=chat_session_id,
        channel_name=channel_name,
        user_intent=user_intent,
        lang=lang,
        interface_language=interface_language,
        item_type=item_type,
        why_want_to_save_memory=why,
        headword=headword,
        mean_summary=mean,
        conversation_context=ctx,
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
        section = _format_event_section(e)
        assert "## Event" in section
        assert "- chat_session_id: cs-1" in section
        assert "- entry_id: entry-uuid-1" in section
        assert "- timestamp: 2026-11-21 14:58:56" in section
        assert "- channel_name: StdioChannel" in section
        assert "- item_type: vocab" in section
        assert "- why_want_to_save_memory: 用户明确要求记住知识点" in section
        assert "- user_intent: dict" in section
        assert "- lang: en" in section
        assert "- headword: gcc" in section
        assert "### mean_summary" in section
        assert "GNU C 编译器" in section
        assert "### conversation_context" in section
        assert "用户在查词" in section

    def test_section_keeps_multiline_summary(self):
        e = _entry(mean="第一行\n第二行\n第三行")
        section = _format_event_section(e)
        assert "第一行\n第二行\n第三行" in section
        assert "### mean_summary\n第一行\n第二行\n第三行" in section


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
        assert "- headword: gcc" in text
        assert "### mean_summary" in text
        assert "GNU C 编译器" in text
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
                    headword="kernel",
                )))
        f = tmp_vault / "events/2026/11/2026-11-21.md"
        text = f.read_text(encoding="utf-8")
        assert text.count("## Event") == 2
        assert "gcc" in text
        assert "kernel" in text
        assert text.count("# 当天事件") == 1
        assert any("events: appended" in r.message for r in caplog.records)


# ── system prompt ──────────────────────────────────────────────


class TestWriterSystemPrompt:
    def test_includes_vault_spec_sections(self):
        prompt = _build_writer_system_prompt()
        assert "Memory Vault" in prompt
        assert "遇到记录" in prompt
        assert "chat_session_id" in prompt

    def test_states_sandbox_rule(self):
        prompt = _build_writer_system_prompt()
        assert "相对 path" in prompt or "相对路径" in prompt

    def test_uses_mcp_tool_names(self):
        """迁移后 system prompt 必须用 MCP 工具名（read/write/grep/...）。"""
        prompt = _build_writer_system_prompt()
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

    def test_states_read_write_once_constraint(self):
        prompt = _build_writer_system_prompt()
        assert "read" in prompt and "write" in prompt
        assert "至多 1 次" in prompt

    def test_includes_pragmatics_fallback_template(self):
        prompt = _build_writer_system_prompt()
        assert "pragmatics" in prompt

    def test_includes_entry_schema(self):
        prompt = _build_writer_system_prompt()
        assert "## 输入 entry 结构" in prompt
        for field in (
            "chat_session_id", "entry_id", "timestamp", "channel_name",
            "item_type", "why_want_to_save_memory", "user_intent",
            "lang", "interface_language", "headword",
            "mean_summary", "conversation_context",
        ):
            assert field in prompt, f"missing entry field: {field}"
        assert "字段补充说明" in prompt

    def test_entry_schema_appears_before_vault_spec(self):
        prompt = _build_writer_system_prompt()
        assert prompt.index("## 输入 entry 结构") < prompt.index(
            "## memory vault 结构"
        )

    def test_injected_spec_headings_nested_under_parent(self):
        prompt = _build_writer_system_prompt()
        assert "### 记忆实体" in prompt
        assert "### 单语言 Memory Vault Spec" in prompt
        for line in prompt.splitlines():
            stripped = line.lstrip()
            assert not stripped.startswith("# 记忆实体"), line
            assert not stripped.startswith("# 单语言 Memory Vault Spec"), line
        assert "## 输入 entry 结构" in prompt
        assert "## memory vault 结构" in prompt

    def test_tells_agent_session_configure_is_auto(self):
        """agent 不需要主动调 session.configure；prompt 应说明宿主代码自动设置。"""
        prompt = _build_writer_system_prompt()
        assert "session.configure" in prompt
        assert "自动" in prompt or "不需要" in prompt or "不应该" in prompt


# ── MemoryWriterAgent 流程测试 ─────────────────────────────────


class TestWriterAgentSync:
    """单 entry 触发一次 agent.ainvoke（per-entry build agent）。"""

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
                    _entry(timestamp="2026-11-21 14:58:56", headword="gcc"),
                    _entry(timestamp="2026-11-21 15:58:56", headword="kernel"),
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
                    _entry(timestamp="2026-11-21 14:58:56", headword="gcc"),
                    _entry(timestamp="2026-11-21 15:58:56", headword="kernel"),
                    _entry(timestamp="2026-11-21 16:58:56", headword="make"),
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
                agent._process_batch([_entry(headword="gcc")])
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
                        _entry(headword="gcc"),
                        _entry(headword="kernel"),
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
                            [_entry(headword="ambiguous")]
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

    def test_write_kb_item_system_prompt_no_lang_prefix(self):
        prompt = _build_writer_system_prompt()
        assert "$lang/items/" not in prompt
        assert "$lang/events/" not in prompt
        assert "items/<item_type>" in prompt
        assert "items/vocab/" in prompt
        assert "memory/languages/$lang/vault" in prompt


# ── 异步守护线程测试 ──────────────────────────────────────────


class TestWriterAgentDaemon:
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
                agent.enqueue([_entry(headword="gcc")])

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
                agent.enqueue([_entry(headword="a")])

                deadline = time.time() + 2.0
                while time.time() < deadline and not first_called.called:
                    time.sleep(0.01)
                assert first_called.called

            mock_agent.ainvoke = MagicMock(
                return_value={"messages": [AIMessage(content="ok")]}
            )
            with mcp_inmem_server():
                with caplog.at_level(logging.ERROR, logger="everlingo"):
                    agent.enqueue([_entry(headword="b")])

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
