"""WS-Master FastAPI 应用 — Internal API 端点。

监听 8101 端口，所有请求校验 X-Master-Token 头。
按 internal-api-contract.md 实现所有端点。
"""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .config import MasterConfig
from .db import get_conn
from .lifecycle import ContainerLifecycle
from .pat_utils import hash_token
from .repo import IdentityRepo, PatRepo, UserRepo, WsContainerRepo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App state
# ---------------------------------------------------------------------------


class AppState:
    def __init__(self, config: MasterConfig) -> None:
        self.config = config
        self.conn = get_conn(config.db)
        self.user_repo = UserRepo(self.conn)
        self.pat_repo = PatRepo(self.conn)
        self.ws_repo = WsContainerRepo(self.conn)
        self.identity_repo = IdentityRepo(self.conn)
        self.lifecycle = ContainerLifecycle(config, self.ws_repo, self.user_repo)


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------


def _error(code: str, message: str, status: int = 400, details: Optional[dict] = None) -> HTTPException:
    body = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return HTTPException(status_code=status, detail=body)


def _ok(data: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(content=data, status_code=status)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


async def _master_token_middleware(request: Request, call_next):
    # Skip healthz (no auth required)
    if request.url.path == "/internal/healthz":
        return await call_next(request)

    state: AppState = request.app.state.state
    token = request.headers.get("X-Master-Token", "")
    if token != state.config.shared_secret:
        return JSONResponse(
            content={"error": {"code": "unauthorized", "message": "Missing or invalid X-Master-Token"}},
            status_code=401,
        )
    return await call_next(request)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI):
    state: AppState = app.state.state
    # Startup: reconcile
    try:
        await state.lifecycle.reconcile()
    except Exception as e:
        logger.warning("Reconciliation failed (docker may not be available): %s", e)

    # Start background healthcheck task
    task = asyncio.create_task(state.lifecycle.healthcheck_loop())
    yield
    # Shutdown
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await state.lifecycle._http_client.aclose()


def create_app(config: MasterConfig) -> FastAPI:
    state = AppState(config)
    app = FastAPI(
        title="WS-Master",
        version="0.1.1-rc.3",
        lifespan=_lifespan,
    )
    app.state.state = state
    app.middleware("http")(_master_token_middleware)

    # ---- Register endpoints ----

    @app.post("/internal/authenticate")
    async def authenticate(request: Request, body: dict):
        state: AppState = request.app.state.state
        username = body.get("username", "")
        password = body.get("password", "")

        user = state.user_repo.get_by_name(username)
        if user is None:
            raise _error("invalid_credentials", "Invalid username or password", status=401)

        # Verify password
        from .cli import _check_password
        if not _check_password(password, user.password_hash):
            raise _error("invalid_credentials", "Invalid username or password", status=401)

        return _ok({
            "user_id": user.user_id,
            "user_name": user.user_name,
            "display_name": user.user_display_name,
        })

    @app.post("/internal/pat/verify")
    async def pat_verify(request: Request, body: dict):
        state: AppState = request.app.state.state
        token = body.get("token", "")

        hashed = hash_token(token)
        pat = state.pat_repo.verify(hashed)
        if pat is None:
            raise _error("invalid_token", "Invalid or expired token", status=401)

        # Touch last_used_at
        state.pat_repo.touch_last_used(pat.id)

        user = state.user_repo.get_by_id(pat.user_id)
        if user is None:
            raise _error("invalid_token", "Token owner not found", status=401)

        return _ok({
            "user_id": user.user_id,
            "user_name": user.user_name,
            "display_name": user.user_display_name,
        })

    @app.post("/internal/pat")
    async def pat_create(request: Request, body: dict):
        state: AppState = request.app.state.state
        user_id = body.get("user_id", "")
        label = body.get("label", "")
        expires_at = body.get("expires_at")

        if not label:
            raise _error("invalid_request", "Missing required field: label", status=400)

        user = state.user_repo.get_by_id(user_id)
        if user is None:
            raise _error("user_not_found", f"User {user_id} not found", status=404)

        from .pat_utils import generate_pat
        plain, hashed = generate_pat()
        pat = state.pat_repo.add(user_id, hashed, label, expires_at)

        return _ok({
            "id": pat.id,
            "token": plain,
            "user_id": pat.user_id,
            "label": pat.label,
            "created_at": pat.created_at,
            "expires_at": pat.expires_at,
        }, status=201)

    @app.get("/internal/users/{user_id}")
    async def get_user(request: Request, user_id: str):
        state: AppState = request.app.state.state
        user = state.user_repo.get_by_id(user_id)
        if user is None:
            raise _error("user_not_found", f"User {user_id} not found", status=404)
        return _ok({
            "user_id": user.user_id,
            "user_name": user.user_name,
            "display_name": user.user_display_name,
            "created_at": user.created_at,
        })

    @app.get("/internal/users/{user_id}/ws")
    async def list_user_ws(request: Request, user_id: str):
        state: AppState = request.app.state.state
        user = state.user_repo.get_by_id(user_id)
        if user is None:
            raise _error("user_not_found", f"User {user_id} not found", status=404)

        containers = state.ws_repo.list_by_user(user_id)
        return _ok([
            {
                "ws_container_id": ws.ws_container_id,
                "status": ws.status,
                "is_default": ws.is_default,
                "container_name": ws.container_name,
            }
            for ws in containers
        ])

    @app.get("/internal/users/{user_id}/pat")
    async def list_user_pat(request: Request, user_id: str):
        state: AppState = request.app.state.state
        user = state.user_repo.get_by_id(user_id)
        if user is None:
            raise _error("user_not_found", f"User {user_id} not found", status=404)

        pats = state.pat_repo.list_by_user(user_id)
        return _ok([
            {
                "id": pat.id,
                "label": pat.label,
                "created_at": pat.created_at,
                "last_used_at": pat.last_used_at,
                "expires_at": pat.expires_at,
            }
            for pat in pats
        ])

    @app.get("/internal/users/{user_id}/default-ws/backend")
    async def get_default_backend(request: Request, user_id: str):
        state: AppState = request.app.state.state
        user = state.user_repo.get_by_id(user_id)
        if user is None:
            raise _error("user_not_found", f"User {user_id} not found", status=404)

        ws = state.ws_repo.get_default(user_id)
        if ws is None:
            raise _error("no_default_ws", f"No default ws-container for user {user_id}", status=404)

        backend_url, status = await state.lifecycle.ensure_started(ws.ws_container_id)
        if status == "started":
            return _ok({
                "ws_container_id": ws.ws_container_id,
                "backend_url": backend_url,
                "status": status,
            })
        else:
            raise _error(
                "backend_unavailable",
                f"Backend unavailable (status={status})",
                status=503,
                details={"status": status},
            )

    @app.get("/internal/ws/{ws_container_id}/backend")
    async def get_ws_backend(request: Request, ws_container_id: str):
        state: AppState = request.app.state.state
        ws = state.ws_repo.get_by_id(ws_container_id)
        if ws is None:
            raise _error("ws_not_found", f"ws-container {ws_container_id} not found", status=404)

        backend_url, status = await state.lifecycle.ensure_started(ws.ws_container_id)
        if status == "started":
            return _ok({
                "ws_container_id": ws.ws_container_id,
                "backend_url": backend_url,
                "status": status,
            })
        else:
            raise _error(
                "backend_unavailable",
                f"Backend unavailable (status={status})",
                status=503,
                details={"status": status},
            )

    @app.post("/internal/ws/{ws_container_id}/ensure_started")
    async def ensure_ws_started(request: Request, ws_container_id: str):
        state: AppState = request.app.state.state
        ws = state.ws_repo.get_by_id(ws_container_id)
        if ws is None:
            raise _error("ws_not_found", f"ws-container {ws_container_id} not found", status=404)

        backend_url, status = await state.lifecycle.ensure_started(ws.ws_container_id)
        if status == "started":
            return _ok({
                "ws_container_id": ws.ws_container_id,
                "backend_url": backend_url,
                "status": status,
            })
        else:
            raise _error(
                "backend_unavailable",
                f"Backend unavailable (status={status})",
                status=503,
                details={"status": status},
            )

    @app.get("/internal/healthz")
    async def healthz(request: Request):
        state: AppState = request.app.state.state
        try:
            # Quick DB check
            state.conn.execute("SELECT 1").fetchone()
            return _ok({"status": "ok"})
        except Exception as e:
            raise _error("unhealthy", str(e), status=503)

    # ---- Exception handler ----
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            content=exc.detail,
            status_code=exc.status_code,
        )

    return app


# ---------------------------------------------------------------------------
# Daemon runner
# ---------------------------------------------------------------------------


def run_daemon(config_path: str) -> None:
    """Start WS-Master daemon."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = MasterConfig.load(config_path)
    app = create_app(config)

    host, port_str = config.listen.split(":")
    port = int(port_str)

    logger.info("Starting WS-Master on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")