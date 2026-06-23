# ref: web-session-acceptor.md — Web Session Acceptor 实现
# 启动 uvicorn FastAPI 服务器，提供 chatbot API 和 SSE 推送。

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from everlingo.gateway.channels.web_channel import WebChannel
from everlingo.gateway.session_acceptor import SessionAcceptor

app = FastAPI()


class MessageBody(BaseModel):
    text: str


# 全局状态，由 acceptor 初始化时注入
_gateway: Any = None
_channels: dict[str, WebChannel] = {}


@app.post("/api/session")
async def create_session():
    """创建新的 chatbot session。

    ref: web-session-acceptor.md — 后端
    返回 session_id，前端用此 id 连接 SSE 和发送消息。
    """
    session_id = str(uuid.uuid4())
    channel = WebChannel()
    _channels[session_id] = channel
    await _gateway.accept_session(channel, session_id)
    return {"session_id": session_id}


@app.post("/api/session/{session_id}/message")
async def send_message(session_id: str, body: MessageBody):
    """接收用户消息，放入对应 WebChannel 的消息队列。

    ref: web-session-acceptor.md — 后端
    """
    channel = _channels.get(session_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Session not found")
    await channel._incoming.put(body.text)
    return {"ok": True}


@app.get("/api/session/{session_id}/events")
async def event_stream(session_id: str, request: Request):
    """SSE 事件流端点。

    ref: web-session-acceptor.md — SSE 协议
    推送类型：typing_hint（typing=True/False）、message
    """
    channel = _channels.get(session_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Session not found")

    client_queue = channel.add_sse_client()

    async def generate():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(client_queue.get(), timeout=30.0)
                    yield event.format_sse()
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            channel.remove_sse_client(client_queue)

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/")
@app.get("/{path:path}")
async def serve_frontend(path: str = ""):
    """提供前端静态文件。"""
    import os

    static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "web", "dist")
    index_path = os.path.join(static_dir, "index.html")

    if not os.path.exists(index_path):
        return {"message": "Frontend not built. Run `npm run build` in the web/ directory."}

    file_path = os.path.join(static_dir, path) if path else index_path
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    return FileResponse(index_path)


class WebSessionAcceptor(SessionAcceptor):
    """Web Session Acceptor。

    ref: /docs/impl-spec/web-session-acceptor.md
    启动 uvicorn 服务器。Session 由前端 API 调用按需创建。
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        self.host = host
        self.port = port

    async def start(self, gateway: Any) -> asyncio.Task:
        global _gateway
        _gateway = gateway

        config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            loop="asyncio",
            log_level="info",
        )
        server = uvicorn.Server(config)
        return asyncio.create_task(server.serve())
