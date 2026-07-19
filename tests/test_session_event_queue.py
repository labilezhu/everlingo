"""
单元测试：Session 事件队列模式（UserMessage / SystemNotice / QuitEvent）

ref: session.md — 系统事件源
"""
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from everlingo.agents.agent import MessageEvent
from everlingo.gateway.channels.channel import ChannelMetadata
from everlingo.gateway.channels.envelope import (
    UserInputEnvelope,
    render_envelope_to_message_text,
    wrap_plain_text,
)
from everlingo.gateway.session import Session
from everlingo.gateway.session_events import SystemNotice
from everlingo.models import UserProfile, UserLanguage


def _make_session(recv_side_effects, profile=None):
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
    channel.recv_envelope = AsyncMock(side_effect=recv_side_effects)
    channel.get_metadata = MagicMock(
        return_value=ChannelMetadata(name="MockChannel")
    )

    agent = MagicMock()
    agent.ainvoke = AsyncMock(return_value=[MessageEvent(text="agent reply")])
    agent.ahandle_system_notice = AsyncMock(
        return_value=[MessageEvent(text="notice reply")]
    )
    agent.aclose = AsyncMock()

    with patch("everlingo.gateway.session.MainAgent", return_value=agent):
        session = Session(channel, profile)
    return session, channel, agent


class TestSessionEventQueue:
    """Session 事件队列核心流程。"""

    def test_user_message_triggers_ainvoke(self):
        """UserMessage 事件触发 agent.ainvoke 并发送回复。"""
        hello_env = wrap_plain_text("hello")
        session, channel, agent = _make_session([hello_env, None])
        asyncio.run(session.run())

        assert agent.ainvoke.call_count == 1
        call_arg = agent.ainvoke.call_args[0][0]
        rendered = render_envelope_to_message_text(hello_env)
        assert call_arg.text == rendered
        channel.send.assert_called_once_with("agent reply")

    def test_system_notice_triggers_ahandle_system_notice(self):
        """SystemNotice 事件触发 agent.ahandle_system_notice 并发送回复。

        使用 asyncio.Queue 模拟 channel.recv_envelope，精确控制读取时序，
        避免 listener 过早退出导致 QueueEvent 淹没系统通知。
        """
        recv_queue: asyncio.Queue = asyncio.Queue()

        async def controlled_recv_envelope():
            return await recv_queue.get()

        session, channel, agent = _make_session([], profile=None)
        channel.recv_envelope = AsyncMock(side_effect=controlled_recv_envelope)

        async def run_with_post():
            async def producer():
                # 先送一个用户消息，让 run 进入处理状态
                await recv_queue.put(wrap_plain_text("hello"))
                await asyncio.sleep(0.01)
                # 再送系统通知
                session.post_event(SystemNotice(
                    source="memory_writer",
                    updated_files=["items/vocab/ufo.md"],
                    update_summary="test summary",
                    title="ufo",
                    lang="en",
                ))
                await asyncio.sleep(0.01)
                # 最后退出
                await recv_queue.put(None)

            await asyncio.gather(session.run(), producer())

        asyncio.run(run_with_post())

        assert agent.ainvoke.call_count == 1
        assert agent.ahandle_system_notice.call_count == 1
        call_notice = agent.ahandle_system_notice.call_args[0][0]
        assert call_notice.title == "ufo"

    def test_quit_event_exits_loop(self):
        """QuitEvent 退出消息循环。"""
        # _channel_listener 在 channel.recv_envelope 返回 None 时会自己入 QuitEvent
        session, channel, agent = _make_session([None])
        asyncio.run(session.run())

        assert agent.ainvoke.call_count == 0
        assert agent.aclose.called

    # ── 交互日志 ──────────────────────────────────────────────────────
    # ref: session.md — 交互日志
    # 验证 [ChatAgent] IN/OUT/NOTICE 日志输出

    def test_user_message_logs_input_output(self, caplog):
        """用户消息处理时记录 [ChatAgent] IN / OUT 日志。"""
        caplog.set_level(logging.DEBUG, logger="everlingo.gateway.session")
        hello_env = wrap_plain_text("hello")
        session, channel, agent = _make_session([hello_env, None])
        asyncio.run(session.run())

        assert "[ChatAgent] IN" in caplog.text
        assert "envelope=" in caplog.text
        assert '"message":"hello"' in caplog.text
        assert "[ChatAgent] OUT[0]" in caplog.text
        assert "'agent reply'" in caplog.text

    def test_user_message_logs_reply_count(self, caplog):
        """多条回复逐条记录 OUT[N]。"""
        caplog.set_level(logging.DEBUG, logger="everlingo.gateway.session")

        agent = MagicMock()
        agent.ainvoke = AsyncMock(return_value=[
            MessageEvent(text="first reply"),
            MessageEvent(text="second reply"),
        ])
        agent.ahandle_system_notice = AsyncMock(return_value=[])
        agent.aclose = AsyncMock()

        channel = MagicMock()
        channel.init = AsyncMock()
        channel.send = AsyncMock()
        channel.send_typing_hint = AsyncMock()
        channel.stop_typing_hint = AsyncMock()
        channel.recv_envelope = AsyncMock(
            side_effect=[wrap_plain_text("hi"), None]
        )
        channel.get_metadata = MagicMock(
            return_value=ChannelMetadata(name="MockChannel")
        )

        with patch("everlingo.gateway.session.MainAgent", return_value=agent):
            session = Session(channel, UserProfile(
                language=UserLanguage(interface_language="zh-CN", target_language="en"),
            ))

        asyncio.run(session.run())

        assert "[ChatAgent] OUT session=" in caplog.text
        assert "replies=2" in caplog.text
        assert "[ChatAgent] OUT[0]" in caplog.text
        assert "'first reply'" in caplog.text
        assert "[ChatAgent] OUT[1]" in caplog.text
        assert "'second reply'" in caplog.text

    def test_system_notice_logs_input_output(self, caplog):
        """系统通知处理时记录 [ChatAgent] NOTICE IN / OUT 日志。"""
        caplog.set_level(logging.DEBUG, logger="everlingo.gateway.session")

        recv_queue: asyncio.Queue = asyncio.Queue()

        async def controlled_recv_envelope():
            return await recv_queue.get()

        session, channel, agent = _make_session([], profile=None)
        channel.recv_envelope = AsyncMock(side_effect=controlled_recv_envelope)

        async def run_with_post():
            async def producer():
                await recv_queue.put(wrap_plain_text("hello"))
                await asyncio.sleep(0.01)
                session.post_event(SystemNotice(
                    source="memory_writer",
                    updated_files=["items/vocab/ufo.md"],
                    update_summary="test summary",
                    title="ufo",
                    lang="en",
                ))
                await asyncio.sleep(0.01)
                await recv_queue.put(None)

            await asyncio.gather(session.run(), producer())

        asyncio.run(run_with_post())

        assert "[ChatAgent] NOTICE IN" in caplog.text
        assert "'ufo'" in caplog.text
        assert "[ChatAgent] NOTICE OUT[0]" in caplog.text
        assert "'notice reply'" in caplog.text

    def test_user_message_no_out_log_on_error(self, caplog):
        """ainvoke 异常时不应有 [ChatAgent] OUT 日志。"""
        caplog.set_level(logging.DEBUG, logger="everlingo.gateway.session")

        channel = MagicMock()
        channel.init = AsyncMock()
        channel.send = AsyncMock()
        channel.send_typing_hint = AsyncMock()
        channel.stop_typing_hint = AsyncMock()
        channel.recv_envelope = AsyncMock(
            side_effect=[wrap_plain_text("crash"), None]
        )
        channel.get_metadata = MagicMock(
            return_value=ChannelMetadata(name="MockChannel")
        )

        agent = MagicMock()
        agent.ainvoke = AsyncMock(side_effect=RuntimeError("LLM crash"))
        agent.aclose = AsyncMock()

        with patch("everlingo.gateway.session.MainAgent", return_value=agent):
            session = Session(channel, UserProfile(
                language=UserLanguage(interface_language="zh-CN", target_language="en"),
            ))

        asyncio.run(session.run())

        # 不应有 OUT 日志行
        assert "[ChatAgent] OUT" not in caplog.text

    def test_post_event_before_run_raises(self):
        """run() 启动前调用 post_event 应抛 RuntimeError。"""
        session, channel, agent = _make_session([None])
        with pytest.raises(RuntimeError, match="not started"):
            session.post_event(SystemNotice(
                source="test", updated_files=[], update_summary="",
                    title="x", lang="en",
            ))

    def test_post_event_routes_notice_to_agent(self):
        """post_event 入队的 SystemNotice 最终到达 agent.ahandle_system_notice。"""
        recv_queue: asyncio.Queue = asyncio.Queue()

        async def controlled_recv_envelope():
            return await recv_queue.get()

        session, channel, agent = _make_session([], profile=None)
        channel.recv_envelope = AsyncMock(side_effect=controlled_recv_envelope)

        notice = SystemNotice(
            source="memory_writer",
            updated_files=["items/vocab/test.md"],
            update_summary="测试",
            title="test",
            lang="en",
        )

        async def run_with_post():
            async def producer():
                await recv_queue.put(wrap_plain_text("user msg"))
                await asyncio.sleep(0.01)
                session.post_event(notice)
                await asyncio.sleep(0.01)
                await recv_queue.put(None)

            await asyncio.gather(session.run(), producer())

        asyncio.run(run_with_post())

        agent.ahandle_system_notice.assert_called_once()
        called_with = agent.ahandle_system_notice.call_args[0][0]
        assert called_with.title == "test"
        assert called_with.update_summary == "测试"
