# ref: docs/impl-spec/workspace-console/architecture.md — Admin socket 接口
# FastAPI app + uvicorn over UDS。与 session task 并行跑在主 asyncio loop
# （仿 web_acceptor.py 的 uvicorn.Server + create_task 模式）。

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from everlingo import workspace

logger = logging.getLogger(__name__)


class StatusResponse(BaseModel):
    """GET /status 响应。"""

    state: str
    qr_url: str | None = None


class LastErrorResponse(BaseModel):
    """GET /last_error 响应。"""

    message: str
    at: str


class OkResponse(BaseModel):
    """POST /shutdown 响应。"""

    ok: bool = True


def admin_socket_path() -> Path:
    """admin IPC unix socket 路径。

    ref: docs/impl-spec/workspace-console/architecture.md — 进程拓扑
    $workspace/plugins/channels/wechat_channel/channel_admin.sock
    """
    return (
        workspace.plugins_dir()
        / "channels"
        / "wechat_channel"
        / "channel_admin.sock"
    )


def create_admin_app(
    state: Any, stop_cb: Callable[[], None] | None = None
) -> FastAPI:
    """创建 admin FastAPI app。

    Args:
        state: WechatAdminState（读取状态）。
        stop_cb: 触发 bot 优雅退出的回调（bot 在 init() 阶段才创建，故传懒回调）。
    """
    app = FastAPI()

    @app.get("/status", response_model=StatusResponse)
    async def status() -> StatusResponse:
        snap = state.snapshot()
        return StatusResponse(state=snap["state"], qr_url=snap["qr_url"])

    @app.get("/last_error")
    async def last_error() -> LastErrorResponse | dict:
        snap = state.snapshot()
        if snap["last_error"] is None:
            return {}
        return LastErrorResponse(
            message=snap["last_error"], at=snap["last_error_at"]
        )

    @app.post("/shutdown", response_model=OkResponse)
    async def shutdown() -> OkResponse:
        if stop_cb is not None:
            await asyncio.to_thread(stop_cb)
        return OkResponse()

    return app


class AdminServer:
    """UDS admin server：在 asyncio loop 内运行，可优雅关闭。"""

    def __init__(self, app: FastAPI, uds_path: Path) -> None:
        self._app = app
        self._uds_path = uds_path
        self._server: uvicorn.Server | None = None

    def _config(self) -> uvicorn.Config:
        return uvicorn.Config(
            self._app,
            uds=str(self._uds_path),
            loop="asyncio",
            log_level="info",
            access_log=False,
        )

    async def run(self) -> None:
        """前台运行直至 request_shutdown() 或收到 SIGINT/SIGTERM。"""
        self._uds_path.parent.mkdir(parents=True, exist_ok=True)
        if self._uds_path.exists():
            self._uds_path.unlink()
        server = uvicorn.Server(self._config())
        self._server = server
        await server.serve()

    def request_shutdown(self) -> None:
        """请求优雅关闭（uvicorn Server.should_exit = True）。"""
        if self._server is not None:
            self._server.should_exit = True
