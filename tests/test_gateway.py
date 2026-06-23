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


class TestSessionAttributes:
    """ref: session.md — Session 新属性"""

    def test_session_has_auto_generated_id(self):
        """Session 创建时自动生成 uuid id。"""
        channel = MagicMock()
        agent = MagicMock()
        session = Session(channel, agent)
        assert session.id is not None
        assert isinstance(session.id, str)
        assert len(session.id) > 0

    def test_session_accepts_custom_id(self):
        """可以传入自定义 id。"""
        channel = MagicMock()
        agent = MagicMock()
        session = Session(channel, agent, id="custom-id-123")
        assert session.id == "custom-id-123"

    def test_session_has_create_time(self):
        """Session 创建时自动生成 create_time。"""
        channel = MagicMock()
        agent = MagicMock()
        session = Session(channel, agent)
        assert session.create_time is not None

    def test_session_title_defaults_empty(self):
        """Session title 默认为空字符串。"""
        channel = MagicMock()
        agent = MagicMock()
        session = Session(channel, agent)
        assert session.title == ""

    def test_session_update_time_updated_after_message(self):
        """update_time 在消息处理后更新。"""
        channel = MagicMock()
        channel.init = AsyncMock()
        channel.send = AsyncMock()
        channel.send_typing_hint = AsyncMock()
        channel.stop_typing_hint = AsyncMock()
        channel.recv = AsyncMock(side_effect=["hello", None])

        agent = MagicMock()
        agent.invoke = MagicMock(return_value=MessageEvent(text="reply"))

        session = Session(channel, agent)
        before = session.update_time
        asyncio.run(session.run())
        assert session.update_time >= before


# ── Gateway ───────────────────────────────────────────────────────────────────

class TestGateway:
    """ref: gateway.md — Gateway 服务"""

    def _make_mock_channel(self):
        """创建带完整 async 方法的 mock channel。"""
        channel = MagicMock()
        channel.init = AsyncMock()
        channel.recv = AsyncMock(return_value=None)
        channel.send = AsyncMock()
        channel.send_typing_hint = AsyncMock()
        channel.stop_typing_hint = AsyncMock()
        return channel

    def test_accept_session_creates_new_session(self):
        """accept_session 创建新 Session 并加入列表。"""
        from everlingo.gateway.gateway import Gateway

        gateway = Gateway()
        gateway._profile = MagicMock()

        channel = self._make_mock_channel()
        task = asyncio.run(gateway.accept_session(channel, "session-1"))
        task.cancel()

        assert "session-1" in gateway.sessions
        assert gateway.sessions["session-1"].channel is channel

    def test_accept_session_resume_replaces_channel(self):
        """已存在的 session_id 视为 resume，替换 channel。"""
        from everlingo.gateway.gateway import Gateway

        gateway = Gateway()
        gateway._profile = MagicMock()

        old_channel = self._make_mock_channel()
        task1 = asyncio.run(gateway.accept_session(old_channel, "session-1"))
        task1.cancel()

        new_channel = self._make_mock_channel()
        task2 = asyncio.run(gateway.accept_session(new_channel, "session-1"))
        task2.cancel()

        assert len(gateway.sessions) == 1
        assert gateway.sessions["session-1"].channel is new_channel

    def test_accept_session_multiple_sessions(self):
        """Gateway 维护多个 Session。"""
        from everlingo.gateway.gateway import Gateway

        gateway = Gateway()
        gateway._profile = MagicMock()

        task1 = asyncio.run(gateway.accept_session(self._make_mock_channel(), "session-1"))
        task1.cancel()
        task2 = asyncio.run(gateway.accept_session(self._make_mock_channel(), "session-2"))
        task2.cancel()

        assert len(gateway.sessions) == 2


# ── SessionAcceptor ──────────────────────────────────────────────────────────

class TestSessionAcceptor:
    """ref: session-acceptor.md — Session Acceptor"""

    def test_stdio_acceptor_submits_creation_request(self):
        """StdioSessionAcceptor 向 gateway 提交创建请求。"""
        from everlingo.gateway.session_acceptor import StdioSessionAcceptor

        gateway = MagicMock()

        async def fake_accept_session(channel, session_id):
            return asyncio.create_task(asyncio.sleep(0))

        gateway.accept_session = AsyncMock(side_effect=fake_accept_session)

        asyncio.run(StdioSessionAcceptor().start(gateway))

        gateway.accept_session.assert_called_once()
        call_args = gateway.accept_session.call_args[0]
        from everlingo.gateway.channels.stdio_channel import StdioChannel
        assert isinstance(call_args[0], StdioChannel)
        assert isinstance(call_args[1], str)
        assert len(call_args[1]) > 0

    def test_wechat_acceptor_submits_creation_request(self):
        """WechatSessionAcceptor 向 gateway 提交创建请求。"""
        from everlingo.gateway.session_acceptor import WechatSessionAcceptor

        gateway = MagicMock()

        async def fake_accept_session(channel, session_id):
            return asyncio.create_task(asyncio.sleep(0))

        gateway.accept_session = AsyncMock(side_effect=fake_accept_session)

        asyncio.run(WechatSessionAcceptor().start(gateway))

        gateway.accept_session.assert_called_once()
        call_args = gateway.accept_session.call_args[0]
        from everlingo.gateway.channels.wechat_channel import WechatChannel
        assert isinstance(call_args[0], WechatChannel)
        assert isinstance(call_args[1], str)
        assert len(call_args[1]) > 0
