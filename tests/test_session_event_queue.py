"""
单元测试：Session 事件队列模式（UserMessage / SystemNotice / QuitEvent）

ref: session.md — 系统事件源
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from everlingo.agents.agent import MessageEvent
from everlingo.gateway.session import Session
from everlingo.gateway.session_events import SystemNotice
from everlingo.gateway.channels.channel import ChannelMetadata
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
    channel.recv = AsyncMock(side_effect=recv_side_effects)
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
        session, channel, agent = _make_session(["hello", None])
        asyncio.run(session.run())

        assert agent.ainvoke.call_count == 1
        call_arg = agent.ainvoke.call_args[0][0]
        assert call_arg.text == "hello"
        channel.send.assert_called_once_with("agent reply")

    def test_system_notice_triggers_ahandle_system_notice(self):
        """SystemNotice 事件触发 agent.ahandle_system_notice 并发送回复。

        使用 asyncio.Queue 模拟 channel.recv，精确控制读取时序，
        避免 listener 过早退出导致 QueueEvent 淹没系统通知。
        """
        recv_queue: asyncio.Queue = asyncio.Queue()

        async def controlled_recv():
            return await recv_queue.get()

        session, channel, agent = _make_session([], profile=None)
        channel.recv = AsyncMock(side_effect=controlled_recv)

        async def run_with_post():
            async def producer():
                # 先送一个用户消息，让 run 进入处理状态
                await recv_queue.put("hello")
                await asyncio.sleep(0.01)
                # 再送系统通知
                session.post_event(SystemNotice(
                    source="memory_writer",
                    updated_files=["items/vocab/ufo.md"],
                    update_summary="test summary",
                    headword="ufo",
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
        assert call_notice.headword == "ufo"

    def test_quit_event_exits_loop(self):
        """QuitEvent 退出消息循环。"""
        # _channel_listener 在 channel.recv 返回 None 时会自己入 QuitEvent
        session, channel, agent = _make_session([None])
        asyncio.run(session.run())

        assert agent.ainvoke.call_count == 0
        assert agent.aclose.called

    def test_post_event_before_run_raises(self):
        """run() 启动前调用 post_event 应抛 RuntimeError。"""
        session, channel, agent = _make_session([None])
        with pytest.raises(RuntimeError, match="not started"):
            session.post_event(SystemNotice(
                source="test", updated_files=[], update_summary="",
                headword="x", lang="en",
            ))

    def test_post_event_routes_notice_to_agent(self):
        """post_event 入队的 SystemNotice 最终到达 agent.ahandle_system_notice。"""
        recv_queue: asyncio.Queue = asyncio.Queue()

        async def controlled_recv():
            return await recv_queue.get()

        session, channel, agent = _make_session([], profile=None)
        channel.recv = AsyncMock(side_effect=controlled_recv)

        notice = SystemNotice(
            source="memory_writer",
            updated_files=["items/vocab/test.md"],
            update_summary="测试",
            headword="test",
            lang="en",
        )

        async def run_with_post():
            async def producer():
                await recv_queue.put("user msg")
                await asyncio.sleep(0.01)
                session.post_event(notice)
                await asyncio.sleep(0.01)
                await recv_queue.put(None)

            await asyncio.gather(session.run(), producer())

        asyncio.run(run_with_post())

        agent.ahandle_system_notice.assert_called_once()
        called_with = agent.ahandle_system_notice.call_args[0][0]
        assert called_with.headword == "test"
        assert called_with.update_summary == "测试"
