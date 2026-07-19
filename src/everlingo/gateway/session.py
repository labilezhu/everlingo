# ref: gateway.md — Session 封装 Channel 实例与 Agent 实例的绑定
# 每个 Session 对象有自己的线程，loop 阻塞读取 channel 的消息。
# 2026-07 改为事件队列模式：channel.recv_envelope() 与系统事件混合为统一事件源。

import asyncio
import logging
import uuid
from datetime import datetime

from .channels.channel import Channel, ChannelMetadata
from .channels.envelope import render_envelope_to_message_text
from .session_events import QuitEvent, SystemNotice, UserMessage
from ..agents.agent import MainAgent, MessageEvent
from ..models import UserProfile

logger = logging.getLogger(__name__)


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

        # 后台协程：把 channel.recv_envelope() 转换成 UserMessage / QuitEvent 入队
        listener = asyncio.create_task(self._channel_listener())

        try:
            while True:
                ev = await self._event_queue.get()
                if isinstance(ev, QuitEvent):
                    break
                if isinstance(ev, UserMessage):
                    await self._handle_user_message(ev)
                elif isinstance(ev, SystemNotice):
                    await self._handle_system_notice(ev)
        finally:
            listener.cancel()
            await self.agent.aclose()

    async def _channel_listener(self) -> None:
        """后台读取 channel（envelope 格式），把用户输入转成事件入队。"""
        while True:
            env = await self.channel.recv_envelope()
            if env is None:
                logger.info("session %s: channel closed, posting QuitEvent", self.id)
                await self._event_queue.put(QuitEvent())
                return
            await self._event_queue.put(UserMessage(envelope=env))

    async def _handle_user_message(self, ev: UserMessage) -> None:
        """处理用户消息：typing hint → ainvoke → send replies。

        ref: ADR 20260719 — 从 envelope 渲染文本后传给 agent.ainvoke
        """
        self.update_time = datetime.now()
        env_json = ev.envelope.model_dump_json(ensure_ascii=False)
        logger.debug(
            "[ChatAgent] IN session=%s channel=%s envelope=%s",
            self.id, self.channel_metadata.name, env_json,
        )
        text = render_envelope_to_message_text(ev.envelope)
        input_msg = MessageEvent(text=text)
        await self.channel.send_typing_hint()
        try:
            replies = await self.agent.ainvoke(input_msg)
        except Exception:
            logger.exception("_handle_user_message: ainvoke failed")
            await self.channel.stop_typing_hint()
            await self.channel.send("出错了，请稍后重试")
            return
        await self.channel.stop_typing_hint()
        logger.debug(
            "[ChatAgent] OUT session=%s channel=%s replies=%d",
            self.id, self.channel_metadata.name, len(replies),
        )
        for i, r in enumerate(replies):
            logger.debug("[ChatAgent] OUT[%d] %r", i, r.text)
        for r in replies:
            await self.channel.send(r.text)

    async def _handle_system_notice(self, notice: SystemNotice) -> None:
        """处理系统通知：交给 Chat Agent（LLM 中介），不发 typing hint。"""
        logger.debug(
            "[ChatAgent] NOTICE IN session=%s channel=%s title=%r files=%s",
            self.id, self.channel_metadata.name, notice.title,
            ", ".join(notice.updated_files),
        )
        try:
            replies = await self.agent.ahandle_system_notice(notice)
        except Exception:
            logger.exception("_handle_system_notice failed")
            return
        logger.debug(
            "[ChatAgent] NOTICE OUT session=%s channel=%s replies=%d",
            self.id, self.channel_metadata.name, len(replies),
        )
        for i, r in enumerate(replies):
            logger.debug("[ChatAgent] NOTICE OUT[%d] %r", i, r.text)
        for r in replies:
            await self.channel.send(r.text)
