# ref: gateway.md — Session 封装 Channel 实例与 Agent 实例的绑定
# 每个 Session 对象有自己的线程，loop 阻塞读取 channel 的消息。
# 2026-07 改为事件队列模式：channel.recv() 与系统事件混合为统一事件源。

import asyncio
import uuid
from datetime import datetime

from .channels.channel import Channel, ChannelMetadata
from .session_events import QuitEvent, SystemNotice, UserMessage
from ..agents.agent import MainAgent, MessageEvent
from ..models import UserProfile


class Session:
    """Session 封装 Channel 与 Agent 的绑定，驱动消息循环。

    ref: /docs/impl-spec/gateway.md — Session
    """

    def __init__(
        self, channel: Channel, profile: UserProfile, id: str | None = None
    ) -> None:
        self.id = id if id is not None else str(uuid.uuid4())
        self.create_time = datetime.now()
        self.update_time = datetime.now()
        self.title = ""
        self.channel = channel
        self.channel_metadata: ChannelMetadata = channel.get_metadata()
        self.agent = MainAgent(profile, self.channel_metadata, channel, session_id=self.id)
        # 统一事件队列：UserMessage / SystemNotice / QuitEvent 均入此队列
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None

    # ── 跨线程事件推送 ───────────────────────────────────────────

    def post_event(self, ev) -> None:
        """线程安全：从任意线程/事件循环向本 Session 推送事件。

        ref: session.md — 系统事件源
        Memory Writer Agent daemon thread 通过此入口推送 SystemNotice。
        """
        if self._loop is None:
            raise RuntimeError("Session not started; post_event requires a running event loop")
        self._loop.call_soon_threadsafe(self._event_queue.put_nowait, ev)

    # ── 消息循环 ─────────────────────────────────────────────────

    async def run(self) -> None:
        """消息循环：从统一事件队列消费事件，处理用户消息与系统通知。

        ref: /docs/impl-spec/gateway.md — Session
        退出时关闭 agent 的 MCP 长连接。
        """
        await self.channel.init()
        self._loop = asyncio.get_running_loop()

        # 后台协程：把 channel.recv() 转换成 UserMessage / QuitEvent 入队
        listener = asyncio.create_task(self._channel_listener())

        try:
            while True:
                ev = await self._event_queue.get()
                if isinstance(ev, QuitEvent):
                    break
                if isinstance(ev, UserMessage):
                    await self._handle_user_message(ev.text)
                elif isinstance(ev, SystemNotice):
                    await self._handle_system_notice(ev)
        finally:
            listener.cancel()
            await self.agent.aclose()

    async def _channel_listener(self) -> None:
        """后台读取 channel，把用户输入转成事件入队。"""
        while True:
            text = await self.channel.recv()
            if text is None:
                await self._event_queue.put(QuitEvent())
                return
            await self._event_queue.put(UserMessage(text=text))

    async def _handle_user_message(self, text: str) -> None:
        """处理用户消息：typing hint → ainvoke → send replies。"""
        self.update_time = datetime.now()
        input_msg = MessageEvent(text=text)
        await self.channel.send_typing_hint()
        replies = await self.agent.ainvoke(input_msg)
        await self.channel.stop_typing_hint()
        for r in replies:
            await self.channel.send(r.text)

    async def _handle_system_notice(self, notice: SystemNotice) -> None:
        """处理系统通知：交给 Chat Agent（LLM 中介），不发 typing hint。"""
        replies = await self.agent.ahandle_system_notice(notice)
        for r in replies:
            await self.channel.send(r.text)
