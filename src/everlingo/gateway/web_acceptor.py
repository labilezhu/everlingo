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
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from everlingo.gateway.channels.envelope import UserInputEnvelope, wrap_plain_text
from everlingo.gateway.channels.web_channel import WebChannel
from everlingo.gateway.session_acceptor import SessionAcceptor
from everlingo.gateway.user_profile_api import router as user_profile_router
from everlingo.gateway.vault_editor_api import router as vault_editor_router
from everlingo.gateway.workspace_console.router import router as workspace_console_router
from everlingo.gateway.backup_api import router as backup_router
from everlingo.i18n.pwa import manifest_text, resolve_manifest_language
from everlingo.setting import load_profile
from everlingo.workspace import indexer_mcp_url_path

app = FastAPI()
app.include_router(user_profile_router)
app.include_router(vault_editor_router)
app.include_router(workspace_console_router)
app.include_router(backup_router)

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
    # interface_language：供 Chrome Extension 首次建 session 时缓存为运行时语言。
    # ref: docs/i18n/i18n.md — Phase 4
    interface_language = getattr(_gateway, "interface_language", None) or "en"
    return {"session_id": session_id, "interface_language": interface_language}


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


# ref: docs/ADR/20260804-web-cache-control.md
# HTML 外壳走 no-store，避免 iOS PWA/Safari 用旧 HTML 引导出失效 JS 导致白屏；
# 带内容 hash 的静态资源走 immutable 长缓存；manifest 走 no-cache（允许更新检测）。
HTML_CACHE_CONTROL = "no-store, must-revalidate"
ASSET_CACHE_CONTROL = "public, max-age=31536000, immutable"
MANIFEST_CACHE_CONTROL = "no-cache"


def _static_response(path: str, media_type: str | None = None, cache: str = HTML_CACHE_CONTROL) -> FileResponse:
    headers = {"Cache-Control": cache}
    return FileResponse(path, media_type=media_type, headers=headers)


PWA_MANIFEST_PLACEHOLDER = "{{pwa_short_name}}"


def _manifest_language(request: Request) -> str:
    """协商 PWA 信息语言：profile 优先，Accept-Language 兜底。

    ref: docs/ADR/20260807-pwa-i18n.md §3.2
    """
    interface_language = None
    try:
        interface_language = load_profile().language.interface_language
    except Exception:
        interface_language = None
    return resolve_manifest_language(
        request.headers.get("Accept-Language"), interface_language
    )


def _serve_manifest(request: Request) -> Response:
    """PWA manifest 动态响应：语言无关字段 + PWA_MANIFEST_TEXT[lang] 合并。

    ref: docs/ADR/20260807-pwa-i18n.md §3.3
    """
    path = os.path.join(_static_dir(), "manifest.webmanifest")
    if not os.path.exists(path):
        return JSONResponse(
            content={"message": "manifest not found. Run `npm run build` in the web/ directory."},
            status_code=503,
        )
    with open(path, encoding="utf-8") as f:
        manifest = json.load(f)
    lang = _manifest_language(request)
    manifest.update({key: manifest_text(lang, key) for key in ("name", "short_name", "description")})
    headers = {"Cache-Control": MANIFEST_CACHE_CONTROL, "Vary": "Accept-Language"}
    return Response(
        content=json.dumps(manifest, ensure_ascii=False),
        media_type="application/manifest+json",
        headers=headers,
    )


def _serve_html_with_i18n(path: str, request: Request, cache: str = HTML_CACHE_CONTROL) -> Response:
    """HTML 外壳动态响应：替换 {{pwa_short_name}} 占位符 + 加 Vary: Accept-Language。

    ref: docs/ADR/20260807-pwa-i18n.md §3.4
    """
    if not os.path.exists(path):
        return JSONResponse(
            content={"message": "Frontend not built. Run `npm run build` in the web/ directory."},
            status_code=503,
        )
    with open(path, encoding="utf-8") as f:
        html = f.read()
    lang = _manifest_language(request)
    short_name = manifest_text(lang, "short_name")
    html = html.replace(PWA_MANIFEST_PLACEHOLDER, short_name)
    headers = {"Cache-Control": cache, "Vary": "Accept-Language"}
    return Response(content=html, media_type="text/html", headers=headers)


@app.get("/manifest.webmanifest")
async def serve_manifest(request: Request):
    return _serve_manifest(request)


@app.get("/editor")
@app.get("/editor/{path:path}")
async def serve_editor(path: str = "", request: Request = None):
    """提供编辑器前端 SPA（dist/editor.html fallback）。"""
    editor_index = os.path.join(_static_dir(), "editor.html")
    return _serve_html_with_i18n(editor_index, request)


@app.get("/console/me")
async def serve_me(request: Request = None):
    """Me 页（Workspace Console 入口）。"""
    index = os.path.join(_static_dir(), "me.html")
    return _serve_html_with_i18n(index, request)


@app.get("/console/me/target-language")
async def serve_target_language(request: Request = None):
    """目标学习语言设置页（Me 页子页）。"""
    index = os.path.join(_static_dir(), "target-language.html")
    return _serve_html_with_i18n(index, request)


@app.get("/console/me/backup")
async def serve_backup(request: Request = None):
    """Memory Vault 远端备份配置页（Me 页子页）。"""
    index = os.path.join(_static_dir(), "backup.html")
    return _serve_html_with_i18n(index, request)


@app.get("/console/me/interface-language")
async def serve_interface_language(request: Request = None):
    """界面语言设置页（Me 页子页 / onboarding step 1）。"""
    index = os.path.join(_static_dir(), "interface-language.html")
    return _serve_html_with_i18n(index, request)


@app.get("/console/web-console")
@app.get("/console/web-console/{path:path}")
async def serve_web_console(path: str = "", request: Request = None):
    """Workspace Console SPA（dist/web-console.html fallback）。"""
    index = os.path.join(_static_dir(), "web-console.html")
    return _serve_html_with_i18n(index, request)


@app.get("/healthz")
async def healthz():
    """gateway 进程就绪自检。

    ref: deploy/ws-container/ws-container-spec.md — image 进程健康检查（healthz）
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
async def serve_frontend(path: str = "", request: Request = None):
    """提供前端静态文件。"""
    static_dir = _static_dir()
    index_path = os.path.join(static_dir, "index.html")

    if not os.path.exists(index_path):
        return {"message": "Frontend not built. Run `npm run build` in the web/ directory."}

    file_path = os.path.join(static_dir, path) if path else index_path
    if os.path.isfile(file_path):
        # 带内容 hash 的构建资源（/assets/**）走 immutable 长缓存；
        # HTML 外壳（占位符替换 + Vary: Accept-Language）与其他静态文件保持 no-store。
        if path.startswith("assets/"):
            return _static_response(file_path, cache=ASSET_CACHE_CONTROL)
        if file_path.endswith(".html"):
            return _serve_html_with_i18n(file_path, request)
        return _static_response(file_path)
    # SPA fallback（history 路由命中到 HTML 外壳）
    return _serve_html_with_i18n(index_path, request)


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
