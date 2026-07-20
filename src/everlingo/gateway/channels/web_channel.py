# ref: web-session-acceptor.md — Web Channel 实现
# 实现 Channel Protocol，使用 asyncio.Queue 做消息缓冲，
# SSE 推送 typing hint 和消息到前端。

import asyncio
import base64
import json
import logging
from datetime import datetime, timezone

from everlingo.gateway.channels.channel import Channel, ChannelMetadata
from everlingo.gateway.channels.envelope import UserInputEnvelope

logger = logging.getLogger(__name__)


class SSEEvent:
    """SSE 推送事件模型。"""

    def __init__(self, event_type: str, **data) -> None:
        self.event_type = event_type
        self.data = data
        self.data["timestamp"] = datetime.now(timezone.utc).isoformat()

    def format_sse(self) -> str:
        """格式化为 SSE 协议文本。"""
        payload = json.dumps(self.data, ensure_ascii=False)
        return f"event: {self.event_type}\ndata: {payload}\n\n"


class WebChannel(Channel):
    """Web Channel 实现。

    ref: web-session-acceptor.md — Web Channel 实现
    - recv: 从 _incoming 队列读取前端发来的消息
    - send/send_typing_hint/stop_typing_hint: 通过 SSE 推送到前端
    - 超时回收：无 SSE client 超过宽限期 / 绝对空闲超时 → recv() 返回 None
    """

    # 超时参数（类常量，可通过构造参数覆盖，方便测试）
    IDLE_CHECK_INTERVAL = 30       # 轮询间隔（秒）
    DISCONNECT_GRACE = 1200        # 无 SSE client 宽限期（秒），默认 20 分钟
    ABSOLUTE_IDLE_TIMEOUT = 3600   # 绝对空闲超时（秒），默认 60 分钟

    def __init__(
        self,
        session_id: str = "",
        *,
        idle_check_interval: int = IDLE_CHECK_INTERVAL,
        disconnect_grace: int = DISCONNECT_GRACE,
        absolute_idle_timeout: int = ABSOLUTE_IDLE_TIMEOUT,
    ) -> None:
        self.session_id = session_id
        self._idle_check_interval = idle_check_interval
        self._disconnect_grace = disconnect_grace
        self._absolute_idle_timeout = absolute_idle_timeout
        self._incoming: asyncio.Queue[UserInputEnvelope | None] = asyncio.Queue()
        self._sse_queues: list[asyncio.Queue[SSEEvent]] = []
        self._lock = asyncio.Lock()

    async def init(self) -> None:
        pass

    async def send_typing_hint(self) -> None:
        await self._broadcast(SSEEvent("typing_hint", typing=True))

    async def stop_typing_hint(self) -> None:
        await self._broadcast(SSEEvent("typing_hint", typing=False))

    async def send(self, content: str) -> None:
        await self._broadcast(SSEEvent("message", text=content))

    async def recv_envelope(self) -> UserInputEnvelope | None:
        """读取前端消息（envelope 格式），支持超时回收。

        ref: ADR 20260719 — 使用 recv_envelope 替代 recv
        - 每 IDLE_CHECK_INTERVAL 秒轮询一次 _incoming 队列
        - 无 SSE client 超过 DISCONNECT_GRACE → 返回 None（触发 QuitEvent）
        - 绝对空闲超过 ABSOLUTE_IDLE_TIMEOUT → 返回 None（触发 QuitEvent）
        """
        no_client_since: datetime | None = None
        last_activity = datetime.now()

        while True:
            try:
                msg = await asyncio.wait_for(
                    self._incoming.get(), timeout=self._idle_check_interval
                )
                last_activity = datetime.now()
                return msg
            except asyncio.TimeoutError:
                now = datetime.now()

                # 绝对空闲超时检查
                idle_seconds = (now - last_activity).total_seconds()
                if idle_seconds > self._absolute_idle_timeout:
                    logger.info(
                        "session %s: ABSOLUTE_IDLE_TIMEOUT (idle %.0fs)",
                        self.session_id, idle_seconds,
                    )
                    return None

                # 无 SSE client 宽限期检查
                if len(self._sse_queues) > 0:
                    no_client_since = None
                elif no_client_since is None:
                    no_client_since = now
                else:
                    grace_seconds = (now - no_client_since).total_seconds()
                    if grace_seconds > self._disconnect_grace:
                        logger.info(
                            "session %s: DISCONNECT_GRACE timeout "
                            "(no SSE client for %.0fs)",
                            self.session_id, grace_seconds,
                        )
                        return None

    async def send_sound(self, content: bytes, format: str) -> None:
        audio_b64 = base64.b64encode(content).decode("ascii")
        await self._broadcast(SSEEvent("sound", audio=audio_b64, format=format))

    def get_metadata(self) -> ChannelMetadata:
        return ChannelMetadata(
            name=type(self).__name__,
            supported_sound_media_format=["mp3"],
        )

    async def _broadcast(self, event: SSEEvent) -> None:
        async with self._lock:
            dead: list[asyncio.Queue[SSEEvent]] = []
            for q in self._sse_queues:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    dead.append(q)
            for q in dead:
                self._sse_queues.remove(q)

    def add_sse_client(self) -> asyncio.Queue[SSEEvent]:
        q: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=128)
        self._sse_queues.append(q)
        return q

    def remove_sse_client(self, q: asyncio.Queue[SSEEvent]) -> None:
        if q in self._sse_queues:
            self._sse_queues.remove(q)
