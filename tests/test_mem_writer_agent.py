"""Memory Writer Agent 核心流程与边缘测试。

ref: docs/impl-spec/memory-writer-agent-spec.md
TEST_STYLE 要求：核心流程相关测试 + 边缘用户输入场景；
避免对 LLM 自然语言文本输出作字符串断言。

测试覆盖：
- ULID 生成格式与唯一性
- 工具沙箱：相对路径约束、../ 逃逸拒绝、tmp/ 支持
- events 追加：文件不存在时建表头、已存在时追加行
- MemoryWriterAgent 生命周期与异步消费
- 单 entry 触发一次 agent.invoke；失败隔离
- gateway.memory_writer 单例代理
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from everlingo import workspace
from everlingo.mem.agents.mem_entries import MemoryEntry
from everlingo.mem.agents.mem_writer_agent import (
    MemoryWriterAgent,
    _append_event,
    _build_writer_system_prompt,
    _events_rel_path,
    _format_event_row,
)
from everlingo.mem.agents.mem_writer_tools import (
    PathSandboxError,
    _gen_ulid,
    _resolve_safe,
    build_mem_writer_tools,
    mem_create_tmp_file,
    mem_grep,
    mem_list_directory,
    mem_read_file,
    mem_remove_file,
    mem_search_files,
    mem_write_file,
)


# ── fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def tmp_memory(monkeypatch, tmp_path):
    """把 workspace.memory_dir() 重定向到 tmp_path/memory。"""
    mem = tmp_path / "memory"
    mem.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("everlingo.workspace.memory_dir", lambda: mem)
    return mem


@pytest.fixture(autouse=True)
def reset_memory_writer_singleton():
    """每个测试后重置 gateway 的 memory_writer 代理，
    避免单例状态泄漏到其它测试。"""
    yield
    from everlingo.gateway import gateway as gw_mod
    proxy = gw_mod.memory_writer
    proxy._agent = None  # type: ignore[attr-defined]


def _entry(
    headword="gcc",
    item_type="vocab",
    why="用户明确要求记住知识点",
    lang="en",
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
        item_type=item_type,
        why_want_to_save_memory=why,
        headword=headword,
        mean_summary=mean,
        conversation_context=ctx,
    )


# ── ULID ──────────────────────────────────────────────────────────────


class TestUlidGen:
    def test_format_is_26_crockford_base32(self):
        ulid = _gen_ulid()
        assert len(ulid) == 26
        alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
        for c in ulid:
            assert c in alphabet

    def test_first_two_chars_indicate_year(self):
        # 标准 ULID 前 48-bit 时间戳，前两字符一般落在 0-7 之间（含 2026 年段）
        ulid = _gen_ulid()
        # 不强制断言具体值（依赖 time.time()），只断言前两字符在合法集合内
        assert ulid[0] in "01234567"

    def test_unique_across_calls(self):
        ids = {_gen_ulid() for _ in range(100)}
        assert len(ids) == 100


# ── 路径沙箱 ──────────────────────────────────────────────────────────


class TestPathSandbox:
    def test_resolve_safe_returns_path_under_memory_dir(self, tmp_memory):
        p = _resolve_safe("items/en/vocab/foo.md")
        assert p == tmp_memory / "items/en/vocab/foo.md"

    def test_resolve_safe_with_empty_path(self, tmp_memory):
        assert _resolve_safe("") == tmp_memory

    def test_resolve_safe_with_dot_path(self, tmp_memory):
        assert _resolve_safe(".") == tmp_memory

    def test_resolve_safe_rejects_parent_escape(self, tmp_memory):
        with pytest.raises(PathSandboxError):
            _resolve_safe("../escape.md")

    def test_resolve_safe_rejects_absolute_path(self, tmp_memory):
        with pytest.raises(PathSandboxError):
            _resolve_safe("/etc/passwd")

    def test_resolve_safe_rejects_hidden_parent_escape(self, tmp_memory):
        # 即使经过子目录再 .. 也应被拒
        with pytest.raises(PathSandboxError):
            _resolve_safe("items/en/../../../escape.md")


# ── mem_* 工具 ────────────────────────────────────────────────────────


class TestMemWriteRead:
    def test_write_creates_parent_dirs_and_file(self, tmp_memory):
        result = mem_write_file.invoke({"path": "items/en/vocab/foo.md",
                                         "content": "hello"})
        assert "ok" in result
        assert (tmp_memory / "items/en/vocab/foo.md").read_text(encoding="utf-8") == "hello"

    def test_write_overwrites_existing(self, tmp_memory):
        p = tmp_memory / "x.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("old", encoding="utf-8")
        mem_write_file.invoke({"path": "x.md", "content": "new"})
        assert p.read_text(encoding="utf-8") == "new"

    def test_read_returns_content(self, tmp_memory):
        p = tmp_memory / "y.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("abc", encoding="utf-8")
        assert mem_read_file.invoke({"path": "y.md"}) == "abc"

    def test_read_missing_file_returns_error(self, tmp_memory):
        out = mem_read_file.invoke({"path": "missing.md"})
        assert "error" in out

    def test_write_rejects_escape(self, tmp_memory):
        with pytest.raises(PathSandboxError):
            mem_write_file.invoke({"path": "../escape.md", "content": "x"})


class TestMemCreateTmpFile:
    def test_creates_file_in_tmp_dir(self, tmp_memory):
        rel = mem_create_tmp_file.invoke({})
        assert rel.startswith("tmp/tmp_")
        assert rel.endswith(".md")
        abs_path = tmp_memory / rel
        assert abs_path.exists()
        assert abs_path.read_text(encoding="utf-8") == ""


class TestMemRemoveFile:
    def test_remove_existing_file(self, tmp_memory):
        p = tmp_memory / "x.md"
        p.write_text("bye", encoding="utf-8")
        out = mem_remove_file.invoke({"path": "x.md"})
        assert "ok" in out
        assert not p.exists()

    def test_remove_missing_returns_error(self, tmp_memory):
        out = mem_remove_file.invoke({"path": "missing.md"})
        assert "error" in out


class TestMemListDirectory:
    def test_lists_direct_children(self, tmp_memory):
        (tmp_memory / "a.md").write_text("1", encoding="utf-8")
        (tmp_memory / "b").mkdir()
        out = mem_list_directory.invoke({"path": ""})
        names = sorted(item["file_name"] for item in out)
        assert names == ["a.md", "b"]

    def test_file_info_shape(self, tmp_memory):
        (tmp_memory / "z.md").write_text("hello", encoding="utf-8")
        out = mem_list_directory.invoke({"path": ""})
        assert len(out) == 1
        item = out[0]
        assert set(item.keys()) == {"file_name", "size_bytes", "create_time", "modify_time"}
        assert item["file_name"] == "z.md"
        assert item["size_bytes"] == 5
        # 时间戳格式 yyyy-mm-dd HH:MM:SS
        assert len(item["create_time"]) == 19


class TestMemSearchFiles:
    def test_glob_star_matches(self, tmp_memory):
        (tmp_memory / "items").mkdir(parents=True, exist_ok=True)
        (tmp_memory / "items" / "gcc--abc.md").write_text("x", encoding="utf-8")
        (tmp_memory / "items" / "foo.md").write_text("x", encoding="utf-8")
        out = mem_search_files.invoke({"path": "items", "pattern": "gcc*.md"})
        names = sorted(item["file_path"] for item in out)
        assert names == ["gcc--abc.md"]

    def test_recursive_search(self, tmp_memory):
        (tmp_memory / "items/en/vocab").mkdir(parents=True, exist_ok=True)
        (tmp_memory / "items/en/vocab/gcc.md").write_text("x", encoding="utf-8")
        (tmp_memory / "items/en/grammar").mkdir(parents=True, exist_ok=True)
        (tmp_memory / "items/en/grammar/foo.md").write_text("x", encoding="utf-8")
        out = mem_search_files.invoke({"path": "items", "pattern": "*.md"})
        assert len(out) == 2


class TestMemGrep:
    def test_finds_matching_line(self, tmp_memory):
        (tmp_memory / "items/en/vocab").mkdir(parents=True, exist_ok=True)
        (tmp_memory / "items/en/vocab/gcc.md").write_text(
            "---\nheadword: gcc\n---\nbody", encoding="utf-8"
        )
        out = mem_grep.invoke({"path": "items", "pattern": r"headword:\s*gcc"})
        assert len(out) == 1
        assert out[0]["file_path"] == "en/vocab/gcc.md"
        assert "headword: gcc" in out[0]["matched_text"]

    def test_no_match_returns_empty(self, tmp_memory):
        (tmp_memory / "items").mkdir(parents=True, exist_ok=True)
        (tmp_memory / "items/x.md").write_text("nothing", encoding="utf-8")
        out = mem_grep.invoke({"path": "items", "pattern": r"zzz"})
        assert out == []


class TestBuildMemWriterTools:
    def test_returns_all_tools(self):
        tools = build_mem_writer_tools()
        names = [t.name for t in tools]
        assert set(names) == {
            "mem_create_tmp_file",
            "mem_read_file",
            "mem_write_file",
            "mem_append_file",
            "mem_remove_file",
            "mem_list_directory",
            "mem_search_files",
            "mem_grep",
            "mem_gen_id",
        }


# ── events 写入（纯代码）─────────────────────────────────────────────


class TestEventsRelPath:
    def test_path_shape(self):
        e = _entry(timestamp="2026-11-21 14:58:56", lang="en")
        assert _events_rel_path(e) == "en/events/2026/11/2026-11-21.md"

    def test_path_handles_japanese_lang(self):
        e = _entry(timestamp="2026-11-21 14:58:56", lang="ja")
        assert _events_rel_path(e).startswith("ja/events/2026/11/")


class TestFormatEventRow:
    def test_row_has_all_columns(self):
        e = _entry()
        row = _format_event_row(e)
        # 11 列
        assert row.count("|") == 12
        assert "gcc" in row
        assert "GNU C 编译器" in row
        assert "cs-1" in row
        assert "StdioChannel" in row

    def test_row_escapes_pipe_in_summary(self):
        e = _entry(mean="a | b")
        row = _format_event_row(e)
        assert "a \\| b" in row


class TestAppendEvent:
    def test_creates_file_with_header_when_missing(self, tmp_memory, caplog):
        import logging as _logging
        with caplog.at_level(_logging.INFO, logger="everlingo"):
            _append_event(_entry(timestamp="2026-11-21 14:58:56", lang="en"))
        f = tmp_memory / "en/events/2026/11/2026-11-21.md"
        assert f.exists()
        text = f.read_text(encoding="utf-8")
        # 表头包含列名
        assert "chat_session_id" in text
        assert "headword" in text
        # 行包含 entry 内容
        assert "gcc" in text
        # 日志：created
        assert any("events: created" in r.message for r in caplog.records)

    def test_appends_to_existing_file(self, tmp_memory, caplog):
        import logging as _logging
        _append_event(_entry(timestamp="2026-11-21 14:58:56", lang="en"))
        with caplog.at_level(_logging.INFO, logger="everlingo"):
            _append_event(_entry(
                timestamp="2026-11-21 15:58:56",
                lang="en",
                headword="kernel",
            ))
        f = tmp_memory / "en/events/2026/11/2026-11-21.md"
        text = f.read_text(encoding="utf-8")
        # 两条 entry 都应在文件中
        assert "gcc" in text
        assert "kernel" in text
        # 日志：appended
        assert any("events: appended" in r.message for r in caplog.records)


# ── system prompt ──────────────────────────────────────────────────────


class TestWriterSystemPrompt:
    def test_includes_vault_spec_sections(self):
        prompt = _build_writer_system_prompt()
        # vault_spec + 展开的 kb_items_spec / events_spec 关键标题应出现
        assert "Memory Vault" in prompt
        assert "Memory Vault" in prompt or "Memory Vault Runtime Spec" in prompt
        # kb_items_spec 展开：vocab 模板中的「遇到记录」章节
        assert "遇到记录" in prompt
        # events_spec 展开：表格列名
        assert "chat_session_id" in prompt

    def test_states_sandbox_rule(self):
        prompt = _build_writer_system_prompt()
        assert "相对 path" in prompt or "相对路径" in prompt

    def test_states_read_write_once_constraint(self):
        prompt = _build_writer_system_prompt()
        assert "mem_read_file" in prompt and "mem_write_file" in prompt
        assert "至多 1 次" in prompt or "1 次" in prompt

    def test_includes_pragmatics_fallback_template(self):
        prompt = _build_writer_system_prompt()
        assert "pragmatics" in prompt


# ── MemoryWriterAgent 同步测试 ───────────────────────────────────────


class TestWriterAgentSync:
    def _make_agent(self, tmp_memory):
        """构造一个 mock 掉 LLM agent 的 MemoryWriterAgent。"""
        with patch("everlingo.mem.agents.mem_writer_agent.create_agent") as mock_create:
            mock_agent = MagicMock()
            mock_agent.invoke = MagicMock(
                return_value={"messages": [AIMessage(content="done")]}
            )
            mock_create.return_value = mock_agent
            agent = MemoryWriterAgent()
        agent._agent = mock_agent  # 再次覆盖以防 create_agent 已被 patch 替换
        return agent, mock_agent

    def test_init_does_not_start_thread(self, tmp_memory):
        with patch("everlingo.mem.agents.mem_writer_agent.create_agent", return_value=MagicMock()):
            agent = MemoryWriterAgent()
        assert agent._thread is None

    def test_process_batch_writes_events_for_each_entry(self, tmp_memory):
        agent, _ = self._make_agent(tmp_memory)
        entries = [
            _entry(timestamp="2026-11-21 14:58:56", headword="gcc"),
            _entry(timestamp="2026-11-21 15:58:56", headword="kernel"),
        ]
        agent._process_batch(entries)

        events_file = tmp_memory / "en/events/2026/11/2026-11-21.md"
        assert events_file.exists()
        text = events_file.read_text(encoding="utf-8")
        assert "gcc" in text
        assert "kernel" in text

    def test_process_batch_invokes_agent_once_per_entry(self, tmp_memory):
        agent, mock_agent = self._make_agent(tmp_memory)
        entries = [
            _entry(timestamp="2026-11-21 14:58:56", headword="gcc"),
            _entry(timestamp="2026-11-21 15:58:56", headword="kernel"),
            _entry(timestamp="2026-11-21 16:58:56", headword="make"),
        ]
        agent._process_batch(entries)

        assert mock_agent.invoke.call_count == 3

    def test_process_batch_passes_entry_to_agent_as_message(self, tmp_memory):
        agent, mock_agent = self._make_agent(tmp_memory)
        entry = _entry(timestamp="2026-11-21 14:58:56", headword="gcc")
        agent._process_batch([entry])

        call_args = mock_agent.invoke.call_args[0][0]
        msgs = call_args["messages"]
        assert any("gcc" in m.content for m in msgs if hasattr(m, "content"))

    def test_events_failure_does_not_block_kb_item_write(self, tmp_memory, caplog):
        """events 追加抛错时，kb item 写入仍应被尝试。"""
        agent, mock_agent = self._make_agent(tmp_memory)

        # 把 _append_event 替换为抛异常的版本
        with patch(
            "everlingo.mem.agents.mem_writer_agent._append_event",
            side_effect=RuntimeError("disk full"),
        ):
            agent._process_batch([_entry()])

        # agent.invoke 仍被调用（kb item 写入尝试）
        assert mock_agent.invoke.call_count == 1

    def test_kb_item_failure_does_not_break_batch(self, tmp_memory, caplog):
        """单条 entry 的 LLM 调用抛错时，batch 中其它 entry 应继续被处理。"""
        import logging as _logging
        agent, mock_agent = self._make_agent(tmp_memory)
        mock_agent.invoke.side_effect = [
            RuntimeError("llm down"),
            {"messages": [AIMessage(content="ok")]},
        ]

        with caplog.at_level(_logging.ERROR, logger="everlingo"):
            agent._process_batch([
                _entry(headword="gcc"),
                _entry(headword="kernel"),
            ])

        # 第二次 invoke 应被调用
        assert mock_agent.invoke.call_count == 2
        # events 写入：两条都尝试（即使 kb item 失败）
        events_file = tmp_memory / "en/events/2026/11/2026-11-21.md"
        text = events_file.read_text(encoding="utf-8")
        assert "gcc" in text
        assert "kernel" in text
        # error 日志
        assert any("kb item write failed" in r.message for r in caplog.records)


# ── MemoryWriterAgent 异步守护线程测试 ─────────────────────────────


class TestWriterAgentDaemon:
    def test_enqueue_does_not_block(self, tmp_memory):
        with patch(
            "everlingo.mem.agents.mem_writer_agent.create_agent"
        ) as mock_create:
            mock_agent = MagicMock()

            def slow_invoke(*args, **kwargs):
                time.sleep(0.3)
                return {"messages": [AIMessage(content="done")]}

            mock_agent.invoke = MagicMock(side_effect=slow_invoke)
            mock_create.return_value = mock_agent
            agent = MemoryWriterAgent()
        agent.start()

        t0 = time.time()
        agent.enqueue([_entry()])
        elapsed = time.time() - t0
        assert elapsed < 0.05
        agent.stop(timeout=2.0)

    def test_run_loop_processes_enqueued_batches(self, tmp_memory):
        with patch(
            "everlingo.mem.agents.mem_writer_agent.create_agent"
        ) as mock_create:
            mock_agent = MagicMock()
            mock_agent.invoke = MagicMock(
                return_value={"messages": [AIMessage(content="ok")]}
            )
            mock_create.return_value = mock_agent
            agent = MemoryWriterAgent()
        agent.start()

        agent.enqueue([_entry(headword="gcc")])

        deadline = time.time() + 2.0
        while time.time() < deadline and mock_agent.invoke.call_count == 0:
            time.sleep(0.01)
        assert mock_agent.invoke.call_count == 1

        events_file = tmp_memory / "en/events/2026/11/2026-11-21.md"
        deadline = time.time() + 1.0
        while time.time() < deadline and not events_file.exists():
            time.sleep(0.01)
        assert events_file.exists()

        agent.stop()

    def test_run_loop_survives_exception_and_continues(self, tmp_memory, caplog):
        """batch 处理抛异常时，守护线程应继续消费后续 batch。"""
        import logging as _logging
        with patch(
            "everlingo.mem.agents.mem_writer_agent.create_agent"
        ) as mock_create:
            mock_agent = MagicMock()
            first_called = MagicMock()

            def first_invoke(*args, **kwargs):
                first_called()
                raise RuntimeError("boom")

            mock_agent.invoke = MagicMock(side_effect=first_invoke)
            mock_create.return_value = mock_agent
            agent = MemoryWriterAgent()
        agent.start()

        agent.enqueue([_entry(headword="a")])

        # 等 daemon 真正消费第一个 batch
        deadline = time.time() + 2.0
        while time.time() < deadline and not first_called.called:
            time.sleep(0.01)
        assert first_called.called

        # 切到正常行为
        mock_agent.invoke = MagicMock(
            return_value={"messages": [AIMessage(content="ok")]}
        )
        agent.enqueue([_entry(headword="b")])

        deadline = time.time() + 2.0
        while time.time() < deadline and mock_agent.invoke.call_count == 0:
            time.sleep(0.01)
        assert mock_agent.invoke.call_count == 1

        # error 日志（_write_kb_item 内部捕获后记录）
        assert any("kb item write failed" in r.message for r in caplog.records)
        agent.stop()

    def test_start_is_idempotent(self, tmp_memory):
        with patch(
            "everlingo.mem.agents.mem_writer_agent.create_agent",
            return_value=MagicMock(),
        ):
            agent = MemoryWriterAgent()
        agent.start()
        t1 = agent._thread
        agent.start()
        assert agent._thread is t1
        agent.stop()


# ── gateway.memory_writer 单例代理 ──────────────────────────────────


class TestGatewayMemoryWriterProxy:
    def test_enqueue_lazily_constructs_and_starts_agent(self, tmp_memory):
        from everlingo.gateway import gateway as gw_mod

        with patch("everlingo.mem.agents.mem_writer_agent.create_agent", return_value=MagicMock()):
            gw_mod.memory_writer.enqueue([_entry()])

        # 触发构造后，代理持有 agent
        assert gw_mod.memory_writer._agent is not None  # type: ignore[attr-defined]
        # 守护线程已启动
        assert gw_mod.memory_writer._agent._thread is not None  # type: ignore[attr-defined]
        # 清理
        gw_mod.memory_writer._agent.stop()  # type: ignore[attr-defined]
        gw_mod.memory_writer._agent = None  # type: ignore[attr-defined]