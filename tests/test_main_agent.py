"""MainAgent 核心流程测试。

ref: chat-agent-spec.md
- _pending_drafts → MemoryEntry 构造 → enqueue
- 游标管理（未触发时推进、触发时切片正确）
- 一轮内多次工具调用累积
"""

from __future__ import annotations

import asyncio
import uuid as _uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from everlingo.agents.agent import (
    MainAgent,
    MessageEvent,
    _now_gmt8_str,
    _render_context_messages,
    _tail_recent_turns,
)
from everlingo.tools.request_memory_extract import _MemoryEntryDraft
from everlingo.gateway.channels.channel import ChannelMetadata
from everlingo.models import UserLanguage, UserProfile


# ── 公共 fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def zh_en_profile():
    return UserProfile(
        language=UserLanguage(interface_language="zh-CN", target_language="en"),
    )


@pytest.fixture
def default_channel_metadata():
    return ChannelMetadata(name="StdioChannel")


@pytest.fixture
def mock_agent_response():
    msg = MagicMock()
    msg.content = "mock reply"
    return {"messages": [msg]}


# ── 工具函数测试 ────────────────────────────────────────────────────


class TestCoreHelpers:
    def test_now_gmt8_str_format(self):
        s = _now_gmt8_str()
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


# ── _tail_recent_turns ────────────────────────────────────────────────


class TestTailRecentTurns:
    """ref: chat-agent-spec.md — "轮"的定义"""

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
        human_count = sum(1 for m in out if isinstance(m, HumanMessage))
        assert human_count == 19
        assert out[0].content == "u6"

    def test_preserves_tool_messages(self):
        msgs = self._make_messages(3)
        out = _tail_recent_turns(msgs)
        tool_count = sum(1 for m in out if isinstance(m, ToolMessage))
        assert tool_count == 3

    def test_empty_messages(self):
        assert _tail_recent_turns([]) == []


# ── MainAgent 构造 ──────────────────────────────────────────────────


class TestMainAgentInit:
    def test_init_does_not_create_extract_agent(self, zh_en_profile):
        """不再创建 MemoryExtractAgent。"""
        mock_channel = MagicMock()
        mock_metadata = ChannelMetadata(name="StdioChannel")
        with patch("everlingo.agents.agent.create_llm", return_value=MagicMock()), \
             patch("everlingo.agents.agent.build_tools", return_value=[]), \
             patch.object(MainAgent, '_ensure_mcp_stream', AsyncMock()):
            agent = MainAgent(
                profile=zh_en_profile,
                channel_metadata=mock_metadata,
                channel=mock_channel,
                session_id="session-xyz",
            )
        assert hasattr(agent, '_pending_drafts')
        assert agent._pending_drafts == []
        assert agent._session_id == "session-xyz"

    def test_session_id_none_falls_back(self, zh_en_profile):
        mock_channel = MagicMock()
        mock_metadata = ChannelMetadata(name="StdioChannel")
        with patch("everlingo.agents.agent.create_llm", return_value=MagicMock()), \
             patch("everlingo.agents.agent.build_tools", return_value=[]), \
             patch.object(MainAgent, '_ensure_mcp_stream', AsyncMock()):
            agent = MainAgent(
                profile=zh_en_profile,
                channel_metadata=mock_metadata,
                channel=mock_channel,
                session_id=None,
            )
        assert agent._session_id  # 非空


# ── _add_pending_drafts 累积 ─────────────────────────────────────────


class TestPendingDrafts:
    def test_accumulates_multiple_calls(self, zh_en_profile):
        mock_channel = MagicMock()
        mock_metadata = ChannelMetadata(name="StdioChannel")
        with patch("everlingo.agents.agent.create_llm", return_value=MagicMock()), \
             patch("everlingo.agents.agent.build_tools", return_value=[]), \
             patch.object(MainAgent, '_ensure_mcp_stream', AsyncMock()):
            agent = MainAgent(
                profile=zh_en_profile,
                channel_metadata=mock_metadata,
                channel=mock_channel,
                session_id="s-1",
            )
        agent._add_pending_drafts([
            _MemoryEntryDraft(item_type="vocab", why_want_to_save_memory="用户明确要求记住知识点", title="hello"),
        ])
        agent._add_pending_drafts([
            _MemoryEntryDraft(item_type="grammar", why_want_to_save_memory="纠正事项", title="go→goes"),
        ])
        assert len(agent._pending_drafts) == 2
        assert agent._pending_drafts[0].title == "hello"
        assert agent._pending_drafts[1].title == "go→goes"


# ── MainAgent 接入测试 ────────────────────────────────────────────────


def _make_main_agent(zh_en_profile):
    """mock 构造 MainAgent，返回 (agent, mock_memory_writer_proxy)。"""
    mock_channel = MagicMock()
    mock_metadata = ChannelMetadata(name="StdioChannel")
    with patch("everlingo.agents.agent.create_llm", return_value=MagicMock()), \
         patch("everlingo.agents.agent.build_tools", return_value=[]), \
         patch.object(MainAgent, '_ensure_mcp_stream', AsyncMock()):
        agent = MainAgent(
            profile=zh_en_profile,
            channel_metadata=mock_metadata,
            channel=mock_channel,
            session_id="session-xyz",
        )
    # mock memory_writer proxy
    mock_writer = MagicMock()
    mock_writer.enqueue = MagicMock()
    return agent, mock_writer


class TestMainAgentWiring:
    def test_no_drafts_does_not_enqueue(self, zh_en_profile, mock_agent_response):
        """不触发 request_memory_extraction 工具时不 enqueue。"""
        mock_inner = MagicMock()
        mock_inner.ainvoke = AsyncMock(return_value=mock_agent_response)
        agent, mock_writer = _make_main_agent(zh_en_profile)

        with patch("everlingo.agents.agent.create_agent", return_value=mock_inner), \
             patch("everlingo.agents.agent.load_profile", return_value=zh_en_profile), \
             patch("everlingo.agents.agent.load_user_doc", return_value=""), \
             patch("everlingo.agents.agent.get_config_version", return_value=999), \
             patch("everlingo.agents.agent.prompt_input_mtime", return_value=0.0), \
             patch("everlingo.agents.agent._get_memory_writer", return_value=mock_writer):
            asyncio.run(agent.ainvoke(MessageEvent(text="hello")))
            asyncio.run(agent.ainvoke(MessageEvent(text="world")))

        mock_writer.enqueue.assert_not_called()

    def test_pending_drafts_enqueues_memory_entries(
        self, zh_en_profile, mock_agent_response
    ):
        """有 pending_drafts 时在 invoke 末尾构造 MemoryEntry 并入队。"""
        mock_inner = MagicMock()
        mock_inner.ainvoke = AsyncMock(return_value=mock_agent_response)
        agent, mock_writer = _make_main_agent(zh_en_profile)

        with patch("everlingo.agents.agent.create_agent", return_value=mock_inner), \
             patch("everlingo.agents.agent.load_profile", return_value=zh_en_profile), \
             patch("everlingo.agents.agent.load_user_doc", return_value=""), \
             patch("everlingo.agents.agent.get_config_version", return_value=999), \
             patch("everlingo.agents.agent.prompt_input_mtime", return_value=0.0), \
             patch("everlingo.agents.agent._get_memory_writer", return_value=mock_writer):
            agent._add_pending_drafts([
                _MemoryEntryDraft(item_type="vocab", why_want_to_save_memory="用户明确要求记住知识点", title="gcc"),
            ])
            asyncio.run(agent.ainvoke(MessageEvent(text="gcc")))

        assert agent._pending_drafts == []  # invoke 应清空
        mock_writer.enqueue.assert_called_once()
        entries = mock_writer.enqueue.call_args[0][0]
        assert len(entries) == 1
        e = entries[0]
        assert e.title == "gcc"
        assert e.item_type == "vocab"
        assert e.why_want_to_save_memory == "用户明确要求记住知识点"
        # 系统字段
        assert e.chat_session_id == "session-xyz"
        assert e.channel_name == "StdioChannel"
        assert e.lang == "en"
        assert e.interface_language == "zh-CN"
        _uuid.UUID(e.entry_id)  # 合法 uuid
        assert len(e.timestamp) == 19
        # 对话消息渲染
        assert "[human] gcc" in e.new_messages
        assert e.context_messages == ""

    def test_accumulated_drafts_enqueued_together(
        self, zh_en_profile, mock_agent_response
    ):
        """一轮 invoke 中多次调用 request_memory_extraction 累积后一次入队。"""
        mock_inner = MagicMock()
        mock_inner.ainvoke = AsyncMock(return_value=mock_agent_response)
        agent, mock_writer = _make_main_agent(zh_en_profile)

        with patch("everlingo.agents.agent.create_agent", return_value=mock_inner), \
             patch("everlingo.agents.agent.load_profile", return_value=zh_en_profile), \
             patch("everlingo.agents.agent.load_user_doc", return_value=""), \
             patch("everlingo.agents.agent.get_config_version", return_value=999), \
             patch("everlingo.agents.agent.prompt_input_mtime", return_value=0.0), \
             patch("everlingo.agents.agent._get_memory_writer", return_value=mock_writer):
            agent._add_pending_drafts([
                _MemoryEntryDraft(item_type="vocab", why_want_to_save_memory="用户明确要求记住知识点", title="gcc"),
            ])
            agent._add_pending_drafts([
                _MemoryEntryDraft(item_type="grammar", why_want_to_save_memory="纠正事项", title="go→goes"),
            ])
            asyncio.run(agent.ainvoke(MessageEvent(text="test")))

        mock_writer.enqueue.assert_called_once()
        entries = mock_writer.enqueue.call_args[0][0]
        assert len(entries) == 2
        assert entries[0].title == "gcc"
        assert entries[1].title == "go→goes"

    def test_cursor_advances_even_without_drafts(
        self, zh_en_profile, mock_agent_response
    ):
        """未触发抽取时游标仍推进，后续触发时未触发轮出现在 context_messages。"""
        mock_inner = MagicMock()
        mock_inner.ainvoke = AsyncMock(return_value=mock_agent_response)
        agent, mock_writer = _make_main_agent(zh_en_profile)

        with patch("everlingo.agents.agent.create_agent", return_value=mock_inner), \
             patch("everlingo.agents.agent.load_profile", return_value=zh_en_profile), \
             patch("everlingo.agents.agent.load_user_doc", return_value=""), \
             patch("everlingo.agents.agent.get_config_version", return_value=999), \
             patch("everlingo.agents.agent.prompt_input_mtime", return_value=0.0), \
             patch("everlingo.agents.agent._get_memory_writer", return_value=mock_writer):
            # 前两轮不触发
            asyncio.run(agent.ainvoke(MessageEvent(text="turn1")))
            asyncio.run(agent.ainvoke(MessageEvent(text="turn2")))
            # 第三轮触发
            agent._add_pending_drafts([
                _MemoryEntryDraft(item_type="vocab", why_want_to_save_memory="Chat Agent 判定", title="turn3"),
            ])
            asyncio.run(agent.ainvoke(MessageEvent(text="turn3")))

        mock_writer.enqueue.assert_called_once()
        entries = mock_writer.enqueue.call_args[0][0]
        assert len(entries) == 1
        e = entries[0]
        # new_messages 只含 turn3
        assert "[human] turn3" in e.new_messages
        # context 含前两轮
        assert "[human] turn1" in e.context_messages
        assert "[human] turn2" in e.context_messages

    def test_pydantic_drafts_regression(self, zh_en_profile, mock_agent_response):
        """回归测试：通过 _add_pending_drafts 传入 pydantic _MemoryEntryDraft 后
        ainvoke 不抛 TypeError（Bug：dict 下标访问 pydantic 实例）。"""
        mock_inner = MagicMock()
        mock_inner.ainvoke = AsyncMock(return_value=mock_agent_response)
        agent, mock_writer = _make_main_agent(zh_en_profile)

        with patch("everlingo.agents.agent.create_agent", return_value=mock_inner), \
             patch("everlingo.agents.agent.load_profile", return_value=zh_en_profile), \
             patch("everlingo.agents.agent.load_user_doc", return_value=""), \
             patch("everlingo.agents.agent.get_config_version", return_value=999), \
             patch("everlingo.agents.agent.prompt_input_mtime", return_value=0.0), \
             patch("everlingo.agents.agent._get_memory_writer", return_value=mock_writer):
            agent._add_pending_drafts([
                _MemoryEntryDraft(item_type="vocab", why_want_to_save_memory="用户明确要求记住知识点", title="ambiguous"),
            ])
            replies = asyncio.run(agent.ainvoke(MessageEvent(text="记住 ambiguous 这个词")))

        # 不抛异常、drafts 已清空、writer 收到 entry
        assert agent._pending_drafts == []
        mock_writer.enqueue.assert_called_once()
        entries = mock_writer.enqueue.call_args[0][0]
        assert len(entries) == 1
        assert entries[0].title == "ambiguous"
        assert entries[0].item_type == "vocab"
