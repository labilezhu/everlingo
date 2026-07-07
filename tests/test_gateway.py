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
from everlingo.gateway.channels.channel import ChannelMetadata
from everlingo.models import UserProfile, UserLanguage


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


class TestStdioChannelMetadata:
    """ref: channel-stdio.md — get_metadata"""

    def test_get_metadata_returns_channel_name(self):
        """get_metadata() 返回 StdioChannel 名称和默认值。"""
        channel = StdioChannel()
        metadata = channel.get_metadata()
        assert metadata.name == "StdioChannel"
        assert metadata.supported_sound_media_format == []
        assert metadata.channel_prompt == ""


# ── Session ───────────────────────────────────────────────────────────────────

@pytest.fixture
def test_profile():
    """测试用 UserProfile"""
    return UserProfile(
        language=UserLanguage(interface_language="zh-CN", target_language="en"),
    )


class TestSessionRun:
    """ref: gateway.md — Session 消息循环"""

    def _make_session(self, recv_side_effects, agent_reply_text="ok", profile=None):
        """构建带 mock Channel 和 mock Agent 的 Session。"""
        if profile is None:
            profile = UserProfile(
                language=UserLanguage(interface_language="zh-CN", target_language="en"),
            )

        channel = MagicMock()
        channel.init = AsyncMock()
        channel.send = AsyncMock()
        channel.send_typing_hint = AsyncMock()
        channel.stop_typing_hint = AsyncMock()
        channel.recv = AsyncMock(side_effect=recv_side_effects)
        channel.get_metadata = MagicMock(
            return_value=ChannelMetadata(name="MockChannel")
        )

        agent = MagicMock()
        agent.ainvoke = AsyncMock(return_value=[MessageEvent(text=agent_reply_text)])
        agent.aclose = AsyncMock()

        with patch("everlingo.gateway.session.MainAgent", return_value=agent):
            session = Session(channel, profile)
        return session, channel, agent

    def test_run_one_message_then_quit(self):
        """一条消息后 recv 返回 None，循环退出。"""
        session, channel, agent = self._make_session(["hello", None])
        asyncio.run(session.run())

        assert agent.ainvoke.call_count == 1
        call_arg = agent.ainvoke.call_args[0][0]
        assert call_arg.text == "hello"

    def test_run_sends_agent_reply_to_channel(self):
        """Agent 的回复被发回 channel。"""
        session, channel, agent = self._make_session(
            ["translate this", None], agent_reply_text="这是翻译"
        )
        asyncio.run(session.run())

        assert channel.send.call_count == 1
        sent_text = channel.send.call_args[0][0]
        assert sent_text == "这是翻译"

    def test_run_multiple_messages(self):
        """多条消息依次处理。"""
        session, channel, agent = self._make_session(["word1", "word2", None])
        asyncio.run(session.run())

        assert agent.ainvoke.call_count == 2
        assert channel.send.call_count == 2

    def test_run_sends_multiple_replies_per_message(self):
        """Agent 返回多条回复时（如翻译+朗读场景），每条独立 send 形成多个气泡。"""
        session, channel, agent = self._make_session(
            ["translate and read ufo", None],
            agent_reply_text="ignored",
        )
        agent.ainvoke = AsyncMock(return_value=[
            MessageEvent(text="UFO — 不明飞行物"),
            MessageEvent(text="已为你朗读"),
        ])
        asyncio.run(session.run())

        assert channel.send.call_count == 2
        sent_texts = [c.args[0] for c in channel.send.call_args_list]
        assert sent_texts == ["UFO — 不明飞行物", "已为你朗读"]

    def test_run_sends_no_message_when_replies_empty(self):
        """Agent 返回空列表时（如只调用了 voice_speak），不发任何消息。"""
        session, channel, agent = self._make_session(["read ufo", None])
        agent.ainvoke = AsyncMock(return_value=[])
        asyncio.run(session.run())

        channel.send.assert_not_called()

    def test_run_calls_channel_init(self):
        """Session.run() 先调用 channel.init()。"""
        session, channel, _ = self._make_session([None])
        asyncio.run(session.run())

        channel.init.assert_called_once()


class TestSessionAttributes:
    """ref: session.md — Session 新属性"""

    def test_session_has_auto_generated_id(self, test_profile):
        """Session 创建时自动生成 uuid id。"""
        channel = MagicMock()
        channel.get_metadata = MagicMock(
            return_value=ChannelMetadata(name="MockChannel")
        )
        agent = MagicMock()
        with patch("everlingo.gateway.session.MainAgent", return_value=agent):
            session = Session(channel, test_profile)
        assert session.id is not None
        assert isinstance(session.id, str)
        assert len(session.id) > 0

    def test_session_accepts_custom_id(self, test_profile):
        """可以传入自定义 id。"""
        channel = MagicMock()
        channel.get_metadata = MagicMock(
            return_value=ChannelMetadata(name="MockChannel")
        )
        agent = MagicMock()
        with patch("everlingo.gateway.session.MainAgent", return_value=agent):
            session = Session(channel, test_profile, id="custom-id-123")
        assert session.id == "custom-id-123"

    def test_session_has_create_time(self, test_profile):
        """Session 创建时自动生成 create_time。"""
        channel = MagicMock()
        channel.get_metadata = MagicMock(
            return_value=ChannelMetadata(name="MockChannel")
        )
        agent = MagicMock()
        with patch("everlingo.gateway.session.MainAgent", return_value=agent):
            session = Session(channel, test_profile)
        assert session.create_time is not None

    def test_session_title_defaults_empty(self, test_profile):
        """Session title 默认为空字符串。"""
        channel = MagicMock()
        channel.get_metadata = MagicMock(
            return_value=ChannelMetadata(name="MockChannel")
        )
        agent = MagicMock()
        with patch("everlingo.gateway.session.MainAgent", return_value=agent):
            session = Session(channel, test_profile)
        assert session.title == ""

    def test_session_update_time_updated_after_message(self, test_profile):
        """update_time 在消息处理后更新。"""
        channel = MagicMock()
        channel.init = AsyncMock()
        channel.send = AsyncMock()
        channel.send_typing_hint = AsyncMock()
        channel.stop_typing_hint = AsyncMock()
        channel.recv = AsyncMock(side_effect=["hello", None])
        channel.get_metadata = MagicMock(
            return_value=ChannelMetadata(name="MockChannel")
        )

        agent = MagicMock()
        agent.ainvoke = AsyncMock(return_value=[MessageEvent(text="reply")])
        agent.aclose = AsyncMock()

        with patch("everlingo.gateway.session.MainAgent", return_value=agent):
            session = Session(channel, test_profile)
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
        channel.get_metadata = MagicMock(
            return_value=ChannelMetadata(name="MockChannel")
        )
        return channel

    def test_accept_session_creates_new_session(self):
        """accept_session 创建新 Session 并加入列表。"""
        from everlingo.gateway.gateway import Gateway

        gateway = Gateway()
        gateway._profile = MagicMock()

        channel = self._make_mock_channel()
        with patch("everlingo.gateway.session.MainAgent"):
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
        with patch("everlingo.gateway.session.MainAgent"):
            task1 = asyncio.run(gateway.accept_session(old_channel, "session-1"))
        task1.cancel()

        new_channel = self._make_mock_channel()
        with patch("everlingo.gateway.session.MainAgent"):
            task2 = asyncio.run(gateway.accept_session(new_channel, "session-1"))
        task2.cancel()

        assert len(gateway.sessions) == 1
        assert gateway.sessions["session-1"].channel is new_channel

    def test_accept_session_multiple_sessions(self):
        """Gateway 维护多个 Session。"""
        from everlingo.gateway.gateway import Gateway

        gateway = Gateway()
        gateway._profile = MagicMock()

        with patch("everlingo.gateway.session.MainAgent"):
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
