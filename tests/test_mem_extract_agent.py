"""Memory Extract Agent 核心流程与边缘测试。

ref: docs/impl-spec/memory-extract-agent-spec.md
TEST_STYLE 要求：核心流程相关测试 + 边缘用户输入场景；
避免对 LLM 自然语言文本输出作字符串断言。

本测试文件用 mock 替换 LLM 与 memory_writer，同步执行 _extract() 以便断言，
并对 daemon thread 异步路径与 MainAgent 接入做单独覆盖。
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from everlingo.agents.agent import (
    MainAgent,
    MessageEvent,
    _tail_recent_turns,
)
from everlingo.gateway.channels.channel import ChannelMetadata
from everlingo.mem.agents.mem_entries import (
    ExtractInput,
    ExtractLLMOutput,
    LLMGeneratedEntry,
    MemoryEntry,
)
from everlingo.mem.agents.mem_extract_agent import (
    MemoryExtractAgent,
    _build_system_prompt,
    _intent_mode_label,
    _now_gmt8_str,
    _render_context_messages,
)
from everlingo.models import UserLanguage, UserProfile
from everlingo.utils.md_prompt_compiler import PackageSource, compile_prompt, shift_headings


# ── 公共 fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def zh_en_profile():
    """中文界面，学习英语"""
    return UserProfile(
        language=UserLanguage(interface_language="zh-CN", target_language="en"),
    )


@pytest.fixture
def default_channel_metadata():
    return ChannelMetadata(name="StdioChannel")


@pytest.fixture
def fake_writer():
    """可记录 enqueue 调用的 memory_writer stub。"""
    w = MagicMock()
    w.enqueue = MagicMock()
    return w


@pytest.fixture
def llm_response_factory():
    """构造 ExtractLLMOutput 的工厂。"""

    def _make(entries=None):
        return ExtractLLMOutput(entries=entries or [])

    return _make


def _entry(title="gcc", item_type="vocab", why="用户明确要求记住知识点"):
    """构造 LLM 生成的 entry（不含透传与系统字段）。"""
    return LLMGeneratedEntry(
        item_type=item_type,
        why_want_to_save_memory=why,
        title=title,
    )


@pytest.fixture
def extract_spec_text():
    """从打包默认值编译真实 spec 文本，用作 _build_system_prompt 的测试输入。"""
    source = PackageSource(package="everlingo.mem.vault.vault_specs.default")
    return compile_prompt("memory_extract_spec.md", source)


# ── 数据结构与工具函数 ──────────────────────────────────────────────


class TestUtilityFunctions:
    def test_intent_mode_label_dict(self):
        assert _intent_mode_label("dict") == "dict"

    def test_intent_mode_label_translate(self):
        assert _intent_mode_label("translate") == "translate"

    def test_intent_mode_label_none(self):
        assert _intent_mode_label(None) == "None"

    def test_now_gmt8_str_format(self):
        s = _now_gmt8_str()
        # yyyy-mm-dd HH:MM:SS
        assert len(s) == 19
        assert s[4] == "-" and s[7] == "-" and s[10] == " " and s[13] == ":" and s[16] == ":"

    def test_render_context_messages_basic(self):
        msgs = [
            HumanMessage(content="hello"),
            AIMessage(content="hi there"),
            ToolMessage(content="lookup: gcc = GNU C compiler", tool_call_id="x"),
        ]
        out = _render_context_messages(msgs)
        assert "human" in out
        assert "ai" in out
        assert "tool" in out
        assert "lookup: gcc" in out

    def test_shift_headings_offset_2(self):
        md = "# h1\n## h2\n### h3\n###### h6\nplain"
        out = shift_headings(md, offset=2)
        assert "### h1" in out
        assert "#### h2" in out
        assert "##### h3" in out
        assert "###### h6" in out
        assert "plain" in out


# ── _tail_recent_turns ───────────────────────────────────────────────


class TestTailRecentTurns:
    """ref: memory-extract-agent-spec.md — "轮"的定义 & 为什么分离 new / context"""

    def _make_messages(self, n_human: int):
        msgs = []
        for i in range(n_human):
            msgs.append(HumanMessage(content=f"u{i}"))
            msgs.append(AIMessage(content=f"a{i}"))
            msgs.append(ToolMessage(content=f"t{i}", tool_call_id=str(i)))
        return msgs

    def test_returns_all_when_under_limit(self):
        msgs = self._make_messages(5)
        out = _tail_recent_turns(msgs)
        assert len(out) == len(msgs)

    def test_caps_to_19_turns(self):
        msgs = self._make_messages(25)
        out = _tail_recent_turns(msgs)
        # 应包含最近 19 个 turn，每个 turn 3 条消息
        human_count = sum(1 for m in out if isinstance(m, HumanMessage))
        assert human_count == 19
        # 最早一条应是第 (25-19+1)=7 个 user turn（索引从 0 → u6）
        assert out[0].content == "u6"

    def test_preserves_tool_messages(self):
        msgs = self._make_messages(3)
        out = _tail_recent_turns(msgs)
        tool_count = sum(1 for m in out if isinstance(m, ToolMessage))
        assert tool_count == 3

    def test_empty_messages(self):
        assert _tail_recent_turns([]) == []


# ── _build_system_prompt ─────────────────────────────────────────────


class TestBuildSystemPrompt:
    def test_includes_target_lang(self, zh_en_profile, extract_spec_text):
        prompt = _build_system_prompt(
            target_lang="en",
            interface_lang="zh-CN",
            channel_name="StdioChannel",
            user_doc="",
            vault_spec_content=extract_spec_text,
        )
        assert "en" in prompt
        assert "zh-CN" in prompt

    def test_states_new_context_boundary(self, extract_spec_text):
        prompt = _build_system_prompt(
            target_lang="en",
            interface_lang="zh-CN",
            channel_name="C",
            user_doc="",
            vault_spec_content=extract_spec_text,
        )
        # 应明确区分 new_messages 与 context_messages 的抽取边界
        assert "本轮新增" in prompt
        assert "背景上下文" in prompt
        assert "唯一允许的抽取来源" in prompt
        assert "禁止从中抽取知识点" in prompt

    def test_user_doc_section_skipped_when_empty(self, extract_spec_text):
        prompt = _build_system_prompt(
            target_lang="en",
            interface_lang="zh-CN",
            channel_name="C",
            user_doc="",
            vault_spec_content=extract_spec_text,
        )
        # section header 是唯一的 USER.md 标识；规则文本中也提到 USER.md，
        # 所以检查 section header 而不是子串。
        assert "## 用户个性化偏好 (USER.md)" not in prompt

    def test_user_doc_section_included_when_non_empty(self, extract_spec_text):
        prompt = _build_system_prompt(
            target_lang="en",
            interface_lang="zh-CN",
            channel_name="C",
            user_doc="# 偏好\n- 词源",
            vault_spec_content=extract_spec_text,
        )
        assert "## 用户个性化偏好 (USER.md)" in prompt
        assert "词源" in prompt
        # 标题降级：# → ###（与 _demote_headings 一致）
        assert "### 偏好" in prompt

    def test_user_doc_whitespace_only_skipped(self, extract_spec_text):
        prompt = _build_system_prompt(
            target_lang="en",
            interface_lang="zh-CN",
            channel_name="C",
            user_doc="   \n\n  ",
            vault_spec_content=extract_spec_text,
        )
        assert "## 用户个性化偏好 (USER.md)" not in prompt

    def test_prompt_does_not_request_transparent_fields(self, extract_spec_text):
        """prompt 应明确告知 LLM 不要生成 chat_session_id/entry_id/timestamp 等。"""
        prompt = _build_system_prompt(
            target_lang="en",
            interface_lang="zh-CN",
            channel_name="C",
            user_doc="",
            vault_spec_content=extract_spec_text,
        )
        assert "chat_session_id" in prompt
        assert "entry_id" in prompt
        assert "timestamp" in prompt
        # 应明示"由系统提供" / "系统填充" / "你无需"
        assert any(kw in prompt for kw in ("由系统提供", "系统填充", "你无需"))


# ── MemoryExtractAgent._extract 同步测试 ─────────────────────────────


class TestExtractSync:
    """直接调用 _extract() 做同步断言（覆盖 post-process / 失败处理）。"""

    @pytest.fixture(autouse=True)
    def _patch_extract_spec(self, extract_spec_text):
        """所有 _extract 调用都需要 patch 掉 MCP 依赖。"""
        with patch(
            "everlingo.mem.agents.mem_extract_agent._load_extract_spec_from_vault",
            new_callable=AsyncMock,
            return_value=extract_spec_text,
        ):
            yield

    def _make_agent(self, fake_writer, llm_output):
        """构造一个 mock 掉 LLM 的 MemoryExtractAgent。"""
        agent = MemoryExtractAgent(
            memory_writer=fake_writer,
            chat_session_id="cs-1",
            channel_name="StdioChannel",
            target_lang="en",
            interface_lang="zh-CN",
        )
        agent._llm = MagicMock()
        agent._llm.invoke.return_value = llm_output
        return agent

    def test_post_process_fills_transparent_fields(self, fake_writer, llm_response_factory):
        agent = self._make_agent(fake_writer, llm_response_factory([
            _entry(title="gcc"),
        ]))
        entries = agent._extract(ExtractInput(
            intent_mode="dict",
            new_messages=[HumanMessage(content="gcc")],
            context_messages=[],
        ))
        assert len(entries) == 1
        e = entries[0]
        # 透传字段来自实例属性
        assert e.chat_session_id == "cs-1"
        assert e.channel_name == "StdioChannel"
        assert e.lang == "en"
        assert e.user_intent == "dict"  # intent_mode="dict" → "dict"
        # LLM 生成字段透传
        assert e.title == "gcc"
        # 对话消息渲染
        assert "[human] gcc" in e.new_messages
        assert e.context_messages == ""
        # entry_id 是 uuid4 形式
        import uuid as _uuid
        _uuid.UUID(e.entry_id)  # 解析成功即合法
        # timestamp 是 yyyy-mm-dd HH:MM:SS 格式
        assert len(e.timestamp) == 19

    def test_user_intent_none_label(self, fake_writer, llm_response_factory):
        agent = self._make_agent(fake_writer, llm_response_factory([
            _entry(title="x"),
        ]))
        entries = agent._extract(ExtractInput(
            intent_mode=None, new_messages=[], context_messages=[]
        ))
        assert entries[0].user_intent == "None"

    def test_empty_entries_skip_enqueue(self, fake_writer, llm_response_factory):
        agent = self._make_agent(fake_writer, llm_response_factory([]))
        entries = agent._extract(ExtractInput(
            intent_mode=None, new_messages=[], context_messages=[]
        ))
        assert entries == []
        fake_writer.enqueue.assert_not_called()

    def test_non_empty_entries_call_enqueue(self, fake_writer, llm_response_factory):
        agent = self._make_agent(fake_writer, llm_response_factory([
            _entry(title="gcc"),
            _entry(title="kernel"),
        ]))
        entries = agent._extract(ExtractInput(
            intent_mode=None, new_messages=[], context_messages=[]
        ))
        fake_writer.enqueue.assert_called_once()
        assert len(fake_writer.enqueue.call_args[0][0]) == 2

    def test_llm_exception_in_run_loop_drops_and_continues(
        self, fake_writer, llm_response_factory, caplog
    ):
        """LLM 抛异常时：logger.exception 被调用，enqueue 不被调用，后续任务可继续。"""
        agent = self._make_agent(fake_writer, llm_response_factory([]))
        agent.start()

        # 用一个 event 记录 invoke 第一次被调用，等 daemon 真正进入 _extract 后再 reset side_effect。
        first_called = MagicMock()
        real_invoke = agent._llm.invoke

        def first_invoke(*args, **kwargs):
            first_called()
            raise RuntimeError("llm down")

        agent._llm.invoke.side_effect = first_invoke
        agent.submit(ExtractInput(
            intent_mode=None, new_messages=[], context_messages=[]
        ))

        # 等第一次 invoke 真正发生（daemon thread 已进入 _extract，异常已被 logger.exception 吞掉）
        deadline = time.time() + 2.0
        while time.time() < deadline and not first_called.called:
            time.sleep(0.01)
        assert first_called.called, "daemon thread did not invoke LLM within timeout"

        # 此时切换为正常返回
        agent._llm.invoke = MagicMock(
            return_value=llm_response_factory([_entry(title="ok")])
        )
        agent.submit(ExtractInput(
            intent_mode=None, new_messages=[], context_messages=[]
        ))

        # 等第二次成功 enqueue
        deadline = time.time() + 2.0
        while time.time() < deadline and fake_writer.enqueue.call_count == 0:
            time.sleep(0.01)

        # enqueue 应只被第二次成功调用一次
        assert fake_writer.enqueue.call_count == 1
        assert fake_writer.enqueue.call_args[0][0][0].title == "ok"

        # error 日志应被记录
        assert any("memory extract failed" in r.message for r in caplog.records)
        assert any("cs-1" in r.message for r in caplog.records)

        agent.stop()

    def test_submit_does_not_block(self, fake_writer):
        """submit 应立即返回，不阻塞调用线程。"""
        agent = self._make_agent(fake_writer, ExtractLLMOutput(entries=[]))

        # 把 LLM 改成慢调用
        def slow_invoke(*args, **kwargs):
            time.sleep(0.3)
            return ExtractLLMOutput(entries=[])

        agent._llm.invoke.side_effect = slow_invoke
        agent.start()

        t0 = time.time()
        agent.submit(ExtractInput(
            intent_mode=None, new_messages=[], context_messages=[]
        ))
        elapsed = time.time() - t0
        # 远小于 slow_invoke 的 0.3s
        assert elapsed < 0.05

        # 让消费完成，避免线程残留
        agent.stop(timeout=2.0)

    def test_info_log_contains_all_entry_fields(self, fake_writer, llm_response_factory, caplog):
        """ref: spec — 每个 entry 都应有 info 日志输出全部字段。"""
        import logging as _logging
        agent = self._make_agent(fake_writer, llm_response_factory([
            _entry(title="gcc"),
        ]))
        with caplog.at_level(_logging.INFO, logger="everlingo"):
            agent._extract(ExtractInput(
                intent_mode="dict", new_messages=[], context_messages=[]
            ))

        records = [r for r in caplog.records if "memory extract entry" in r.message]
        assert len(records) == 1
        msg = records[0].message
        # 关键字段名都应在日志中（顺序与实现对齐）
        for field in ["entry_id=", "chat_session_id=", "timestamp=", "channel_name=",
                      "item_type=", "why=", "user_intent=", "lang=",
                      "title=", "new_messages=", "context_messages="]:
            assert field in msg


# ── MainAgent 接入测试 ────────────────────────────────────────────────


def _make_main_agent(zh_en_profile):
    """用 mock 替换 create_llm / build_tools / MCP stream / extract agent 创建 MainAgent。"""
    from everlingo.gateway.channels.channel import ChannelMetadata as _CM
    mock_channel = MagicMock()
    mock_metadata = _CM(name="StdioChannel")
    with patch("everlingo.agents.agent.create_llm", return_value=MagicMock()), \
         patch("everlingo.agents.agent.build_tools", return_value=[]), \
         patch.object(MainAgent, '_ensure_mcp_stream', AsyncMock()), \
         patch("everlingo.agents.agent.MemoryExtractAgent") as mock_extract_cls:
        mock_extract_inst = MagicMock()
        mock_extract_cls.return_value = mock_extract_inst
        agent = MainAgent(
            profile=zh_en_profile,
            channel_metadata=mock_metadata,
            channel=mock_channel,
            session_id="session-xyz",
        )
    return agent, mock_extract_inst


class TestMainAgentWiring:
    def test_main_agent_creates_extract_agent_in_init(self, zh_en_profile):
        """MainAgent.__init__ 应创建并 start 一个 ExtractAgent。"""
        agent, mock_extract_inst = _make_main_agent(zh_en_profile)
        mock_extract_inst.start.assert_called_once()

    def test_invoke_submits_extract_input_with_correct_intent_mode(
        self, zh_en_profile, mock_agent_response
    ):
        """ainvoke() 应在返回 replies 前 submit 一个 ExtractInput，
        intent_mode 与当前 self._intent_mode 一致，且 new/context 切片正确。
        """
        mock_inner = MagicMock()
        mock_inner.ainvoke = AsyncMock(return_value=mock_agent_response)
        agent, mock_extract_inst = _make_main_agent(zh_en_profile)

        # 设置为 dict 模式
        asyncio.run(agent.ainvoke(MessageEvent(text="/dict")))
        # 真实对话触发 submit
        with patch("everlingo.agents.agent.create_agent", return_value=mock_inner), \
             patch("everlingo.agents.agent.load_profile", return_value=zh_en_profile), \
             patch("everlingo.agents.agent.load_user_doc", return_value=""), \
             patch("everlingo.agents.agent.get_config_version", return_value=999), \
             patch("everlingo.agents.agent.prompt_input_mtime", return_value=0.0):
            asyncio.run(agent.ainvoke(MessageEvent(text="hello")))
            asyncio.run(agent.ainvoke(MessageEvent(text="world")))

        # submit 应被调用 2 次（不含命令路径）
        assert mock_extract_inst.submit.call_count == 2

        # 第一次 submit 的 ExtractInput.intent_mode 应是 "dict"
        first_input = mock_extract_inst.submit.call_args_list[0][0][0]
        assert isinstance(first_input, ExtractInput)
        assert first_input.intent_mode == "dict"
        # new_messages 应含本轮 HumanMessage（唯一抽取来源）
        assert any(isinstance(m, HumanMessage) and m.content == "hello"
                   for m in first_input.new_messages)
        # context_messages 不应含本轮 HumanMessage
        assert not any(isinstance(m, HumanMessage) and m.content == "hello"
                       for m in first_input.context_messages)
        # 首轮 context_messages 应为空（游标从 0 起步）
        assert first_input.context_messages == []

        # 第二次 submit：new_messages 应含 "world" 轮，context_messages 应含上一轮 "hello"
        second_input = mock_extract_inst.submit.call_args_list[1][0][0]
        assert any(isinstance(m, HumanMessage) and m.content == "world"
                   for m in second_input.new_messages)
        assert not any(isinstance(m, HumanMessage) and m.content == "world"
                       for m in second_input.context_messages)
        assert any(isinstance(m, HumanMessage) and m.content == "hello"
                   for m in second_input.context_messages)

    def test_cursor_advances_so_old_turns_never_re_extracted(
        self, zh_en_profile, mock_agent_response
    ):
        """ref: spec — 抽取边界硬约束：同一段历史不应在后续轮被放入 new_messages。"""
        mock_inner = MagicMock()
        mock_inner.ainvoke = AsyncMock(return_value=mock_agent_response)
        agent, mock_extract_inst = _make_main_agent(zh_en_profile)

        with patch("everlingo.agents.agent.create_agent", return_value=mock_inner), \
             patch("everlingo.agents.agent.load_profile", return_value=zh_en_profile), \
             patch("everlingo.agents.agent.load_user_doc", return_value=""), \
             patch("everlingo.agents.agent.get_config_version", return_value=999), \
             patch("everlingo.agents.agent.prompt_input_mtime", return_value=0.0):
            asyncio.run(agent.ainvoke(MessageEvent(text="turn1")))
            asyncio.run(agent.ainvoke(MessageEvent(text="turn2")))
            asyncio.run(agent.ainvoke(MessageEvent(text="turn3")))

        # 三轮后，最新一轮的 new_messages 只应含 "turn3"，前两轮只能在 context
        latest = mock_extract_inst.submit.call_args_list[2][0][0]
        human_in_new = [m.content for m in latest.new_messages
                        if isinstance(m, HumanMessage)]
        assert human_in_new == ["turn3"]
        # 前两轮 HumanMessage 必须出现在 context_messages（背景）
        ctx_humans = [m.content for m in latest.context_messages
                      if isinstance(m, HumanMessage)]
        assert "turn1" in ctx_humans
        assert "turn2" in ctx_humans

    def test_command_path_does_not_submit(self, zh_en_profile, mock_agent_response):
        """/dict 等命令路径不应触发 submit。"""
        agent, mock_extract_inst = _make_main_agent(zh_en_profile)

        asyncio.run(agent.ainvoke(MessageEvent(text="/dict")))
        asyncio.run(agent.ainvoke(MessageEvent(text="/help")))

        mock_extract_inst.submit.assert_not_called()

    def test_extract_agent_uses_session_id_and_channel_name(self, zh_en_profile):
        """Extract Agent 构造时应传入 session_id 与 channel_name（来自 channel_metadata）。"""
        with patch("everlingo.agents.agent.create_llm", return_value=MagicMock()), \
             patch("everlingo.agents.agent.build_tools", return_value=[]), \
             patch.object(MainAgent, '_ensure_mcp_stream', AsyncMock()), \
             patch("everlingo.agents.agent.MemoryExtractAgent") as mock_cls:
            mock_extract_inst = MagicMock()
            mock_cls.return_value = mock_extract_inst
            mock_channel = MagicMock()
            mock_metadata = ChannelMetadata(name="WechatChannel")
            MainAgent(
                profile=zh_en_profile,
                channel_metadata=mock_metadata,
                channel=mock_channel,
                session_id="abc-123",
            )

        kwargs = mock_cls.call_args.kwargs
        assert kwargs["chat_session_id"] == "abc-123"
        assert kwargs["channel_name"] == "WechatChannel"
        assert kwargs["target_lang"] == "en"
        assert kwargs["interface_lang"] == "zh-CN"

    def test_session_id_none_falls_back_to_placeholder(self, zh_en_profile):
        """session_id 为 None 时不应让 Extract Agent 收到空字符串。"""
        with patch("everlingo.agents.agent.create_llm", return_value=MagicMock()), \
             patch("everlingo.agents.agent.build_tools", return_value=[]), \
             patch.object(MainAgent, '_ensure_mcp_stream', AsyncMock()), \
             patch("everlingo.agents.agent.MemoryExtractAgent") as mock_cls:
            mock_extract_inst = MagicMock()
            mock_cls.return_value = mock_extract_inst
            mock_channel = MagicMock()
            mock_metadata = ChannelMetadata(name="StdioChannel")
            MainAgent(
                profile=zh_en_profile,
                channel_metadata=mock_metadata,
                channel=mock_channel,
                session_id=None,
            )

        kwargs = mock_cls.call_args.kwargs
        assert kwargs["chat_session_id"]  # 非空


@pytest.fixture
def mock_agent_response():
    """构造一个假的 agent invoke 返回值。"""
    msg = MagicMock()
    msg.content = "mock reply"
    return {"messages": [msg]}
