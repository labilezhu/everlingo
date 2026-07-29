# ref: web-session-acceptor.md — Web Session Acceptor 实现
# 启动 uvicorn FastAPI 服务器，提供 chatbot API 和 SSE 推送。

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Union

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from everlingo.gateway.channels.envelope import UserInputEnvelope, wrap_plain_text
from everlingo.gateway.channels.web_channel import WebChannel
from everlingo.gateway.session_acceptor import SessionAcceptor
from everlingo.gateway.vault_editor_api import router as vault_editor_router
from everlingo.workspace import indexer_mcp_url_path

app = FastAPI()
app.include_router(vault_editor_router)

# MVP: 允许扩展跨源请求（扩展 origin = chrome-extension://<id>）
# 生产前应收敛 allow_origins 到白名单
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)


class TextMessageBody(BaseModel):
    text: str


class EnvelopeMessageBody(BaseModel):
    envelope: UserInputEnvelope


MessageBody = Union[TextMessageBody, EnvelopeMessageBody]


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
    channel = WebChannel(session_id=session_id)
    _channels[session_id] = channel
    task = await _gateway.accept_session(channel, session_id)
    task.add_done_callback(
        lambda _: _channels.pop(session_id, None)
    )
    return {"session_id": session_id}


@app.post("/api/session/{session_id}/message")
async def send_message(session_id: str, body: MessageBody):
    """接收用户消息（纯文本或 envelope），放入对应 WebChannel 的消息队列。

    ref: web-session-acceptor.md — 后端
    ref: ADR 20260719 — MessageBody 改为 union（text / envelope）
    """
    channel = _channels.get(session_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if isinstance(body, EnvelopeMessageBody):
        env = body.envelope
    else:
        env = wrap_plain_text(body.text)
    await channel._incoming.put(env)
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


def _static_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "..", "..", "..", "web", "dist")


@app.get("/manifest.webmanifest")
async def serve_manifest():
    path = os.path.join(_static_dir(), "manifest.webmanifest")
    if not os.path.exists(path):
        return {"message": "manifest not found. Run `npm run build` in the web/ directory."}
    return FileResponse(path, media_type="application/manifest+json")


@app.get("/editor")
@app.get("/editor/{path:path}")
async def serve_editor(path: str = ""):
    """提供编辑器前端 SPA（dist/editor.html fallback）。"""
    editor_index = os.path.join(_static_dir(), "editor.html")

    if not os.path.exists(editor_index):
        return {"message": "Frontend not built. Run `npm run build` in the web/ directory."}

    return FileResponse(editor_index)


@app.get("/healthz")
async def healthz():
    """gateway 进程就绪自检。

    ref: docs/impl-spec/deploy/image/ws-container-spec.md — image 进程健康检查（healthz）
    供 WS-Master lazy start 探活与 docker HEALTHCHECK 使用。

    就绪判定（本地同步、无网络 IO，不依赖外部超时）：
    - `_gateway` 未注入 → 503（acceptor 尚未初始化）
    - `indexer.mcp.url` 文件不存在 → 503（indexer 未就绪）
    - 否则 → 200

    不深入校验 indexer 端口连通 / LLM 可达性：entrypoint.sh 已保证 gateway
    启动时 indexer 端口连通，运行中崩溃由 WS-Master healthcheck task 兜底；
    LLM 调用在请求时按需失败重试。
    """
    if _gateway is None:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "reason": "gateway_not_initialized"},
        )
    if not indexer_mcp_url_path().exists():
        return JSONResponse(
            status_code=503,
            content={"status": "error", "reason": "indexer_not_ready"},
        )
    return {"status": "ok"}


@app.get("/")
@app.get("/{path:path}")
async def serve_frontend(path: str = ""):
    """提供前端静态文件。"""
    static_dir = _static_dir()
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
            timeout_graceful_shutdown=2.0,
        )
        server = uvicorn.Server(config)
        return asyncio.create_task(server.serve())
