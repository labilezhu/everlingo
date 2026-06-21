# ref: web-session-acceptor.md — Web Channel 实现
# 实现 Channel Protocol，使用 asyncio.Queue 做消息缓冲，
# SSE 推送 typing hint 和消息到前端。

import asyncio
import json
from datetime import datetime, timezone


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


class WebChannel:
    """Web Channel 实现。

    ref: /docs/impl-spec/web-session-acceptor.md
    - recv: 从 _incoming 队列读取前端发来的消息
    - send/send_typing_hint/stop_typing_hint: 通过 SSE 推送到前端
    """

    def __init__(self) -> None:
        self._incoming: asyncio.Queue[str | None] = asyncio.Queue()
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

    async def recv(self) -> str | None:
        return await self._incoming.get()

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
