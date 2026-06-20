"""
核心流程测试：StdioChannel、Session、Gateway

ref: TEST_STYLE.md — 只测核心流程和用户输入边缘情况
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from everlingo.agents.agent import MessageEvent
from everlingo.gateway.channels.stdio_channel import StdioChannel
from everlingo.gateway.session import Session


# ── StdioChannel ─────────────────────────────────────────────────────────────

class TestStdioChannelRecv:
    """ref: channel-stdio.md — recv 行为"""

    def test_recv_returns_user_input(self):
        """正常输入返回用户文字。"""
        channel = StdioChannel()
        with patch("builtins.input", return_value="hello"):
            result = asyncio.run(channel.recv())
        assert result == "hello"

    def test_recv_returns_none_on_quit(self):
        """用户输入 /quit 时返回 None。"""
        channel = StdioChannel()
        with patch("builtins.input", return_value="/quit"), \
             patch("builtins.print"):
            result = asyncio.run(channel.recv())
        assert result is None

    def test_recv_returns_none_on_eof(self):
        """stdin EOF 时返回 None。"""
        channel = StdioChannel()
        with patch("builtins.input", side_effect=EOFError), \
             patch("builtins.print"):
            result = asyncio.run(channel.recv())
        assert result is None

    def test_recv_returns_none_on_keyboard_interrupt(self):
        """KeyboardInterrupt 时返回 None。"""
        channel = StdioChannel()
        with patch("builtins.input", side_effect=KeyboardInterrupt), \
             patch("builtins.print"):
            result = asyncio.run(channel.recv())
        assert result is None

    def test_recv_quit_case_insensitive(self):
        """/QUIT 大写也视为退出命令。"""
        channel = StdioChannel()
        with patch("builtins.input", return_value="/QUIT"), \
             patch("builtins.print"):
            result = asyncio.run(channel.recv())
        assert result is None

    def test_send_prints_content(self):
        """send 将消息输出到 stdout。"""
        channel = StdioChannel()
        with patch("builtins.print") as mock_print:
            asyncio.run(channel.send("test message"))
        mock_print.assert_called_once_with("\ntest message\n")


# ── Session ───────────────────────────────────────────────────────────────────

class TestSessionRun:
    """ref: gateway.md — Session 消息循环"""

    def _make_session(self, recv_side_effects, agent_reply_text="ok"):
        """构建带 mock Channel 和 mock Agent 的 Session。"""
        channel = MagicMock()
        channel.init = AsyncMock()
        channel.send = AsyncMock()
        channel.send_typing_hint = AsyncMock()
        channel.stop_typing_hint = AsyncMock()
        channel.recv = AsyncMock(side_effect=recv_side_effects)

        agent = MagicMock()
        agent.invoke = MagicMock(return_value=MessageEvent(text=agent_reply_text))

        return Session(channel, agent), channel, agent

    def test_run_one_message_then_quit(self):
        """一条消息后 recv 返回 None，循环退出。"""
        session, channel, agent = self._make_session(["hello", None])
        asyncio.run(session.run())

        assert agent.invoke.call_count == 1
        call_arg = agent.invoke.call_args[0][0]
        assert call_arg.text == "hello"

    def test_run_sends_agent_reply_to_channel(self):
        """Agent 的回复被发回 channel。"""
        session, channel, agent = self._make_session(
            ["translate this", None], agent_reply_text="这是翻译"
        )
        asyncio.run(session.run())

        channel.send.assert_called_once()
        sent_text = channel.send.call_args[0][0]
        assert sent_text == "这是翻译"

    def test_run_multiple_messages(self):
        """多条消息依次处理。"""
        session, channel, agent = self._make_session(["word1", "word2", None])
        asyncio.run(session.run())

        assert agent.invoke.call_count == 2
        assert channel.send.call_count == 2

    def test_run_calls_channel_init(self):
        """Session.run() 先调用 channel.init()。"""
        session, channel, _ = self._make_session([None])
        asyncio.run(session.run())

        channel.init.assert_called_once()
