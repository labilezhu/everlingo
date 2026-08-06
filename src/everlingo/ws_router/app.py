"""WS-Router FastAPI 应用 — 认证 + 反代服务。

ref: ws-router.md §4
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from .auth import (
    AuthProvider,
    PasswordAuthProvider,
    create_session_token,
    verify_session_token,
)
from .cache import TTLCache
from .config import RouterConfig
from .master_client import MasterClient
from .middleware import make_auth_middleware, trusted_proxy_middleware
from .proxy import proxy_request

logger = logging.getLogger(__name__)

STATIC_MEDIA_TYPES = {
    "/manifest.webmanifest": "application/manifest+json",
    "/favicon.png": "image/png",
    "/icon-192.png": "image/png",
    "/icon-512.png": "image/png",
    "/icon-512-maskable.png": "image/png",
}


def _static_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "..", "..", "..", "web", "dist")


# ref: docs/ADR/20260804-web-cache-control.md
HTML_CACHE_CONTROL = "no-store, must-revalidate"
ASSET_CACHE_CONTROL = "public, max-age=31536000, immutable"
MANIFEST_CACHE_CONTROL = "no-cache"


def _static_response(path: str, media_type: str | None = None, cache: str = HTML_CACHE_CONTROL) -> FileResponse:
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": cache})


class AppState:
    def __init__(self, config: RouterConfig) -> None:
        self.config = config
        self.master = MasterClient(config.master_url, config.master_secret, config.master_timeout)
        self.auth_provider: AuthProvider = PasswordAuthProvider(self.master)
        self.proxy_client = httpx.AsyncClient(timeout=httpx.Timeout(600.0))
        self.pat_cache = TTLCache(maxsize=256, ttl=config.pat_verify_cache_ttl)
        self.backend_cache = TTLCache(maxsize=256, ttl=config.backend_cache_ttl)
        self.me_cache = TTLCache(maxsize=256, ttl=60)

    async def close(self) -> None:
        await self.master.close()
        await self.proxy_client.aclose()

    async def resolve_backend(self, user_id: str) -> str | None:
        cached = self.backend_cache.get(user_id)
        if cached is not None:
            return cached
        info = await self.master.get_default_backend(user_id)
        if info is None:
            return None
        self.backend_cache.set(user_id, info.backend_url)
        return info.backend_url


def create_app(config: RouterConfig) -> FastAPI:
    state = AppState(config)
    app = FastAPI(title="WS-Router", version="0.1.1-rc.6")
    app.state.state = state

    @app.get("/assets/{path:path}", include_in_schema=False)
    async def serve_asset(path: str):
        file = os.path.join(_static_dir(), "assets", path)
        if not os.path.isfile(file):
            return JSONResponse(
                content={"message": "Frontend not built. Run `npm run build` in the web/ directory."},
                status_code=404,
            )
        return _static_response(file, cache=ASSET_CACHE_CONTROL)

    app.middleware("http")(trusted_proxy_middleware)

    app.middleware("http")(
        make_auth_middleware(
            jwt_secret=config.jwt_secret,
            master=state.master,
            pat_cache=state.pat_cache,
            session_ttl=config.session_ttl,
        )
    )

    if config.cors_allow_origins or config.cors_allow_origin_regex:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.cors_allow_origins,
            allow_origin_regex=config.cors_allow_origin_regex,
            allow_methods=["*"],
            allow_headers=["Authorization", "Content-Type"],
            allow_credentials=False,
        )

    @app.get("/login")
    async def get_login(request: Request):
        index = os.path.join(_static_dir(), "login.html")
        if not os.path.exists(index):
            return JSONResponse(
                content={"message": "Frontend not built. Run `npm run build` in the web/ directory."},
                status_code=503,
            )
        return _static_response(index)

    @app.post("/login")
    async def post_login(request: Request):
        body = await request.json()
        username = body.get("username", "")
        password = body.get("password", "")

        user = await state.auth_provider.login(username, password)
        if user is None:
            logger.warning("Login failed: username=%r remote=%s", username, request.client.host if request.client else "?")
            return JSONResponse(
                content={"error": {"code": "invalid_credentials", "message": "Invalid username or password"}},
                status_code=401,
            )

        token = create_session_token(user.user_id, user.user_name, config.jwt_secret, config.session_ttl)
        expires = datetime.now(timezone.utc).isoformat()

        resp = JSONResponse(
            content={
                "user_id": user.user_id,
                "access_token": token,
                "token_type": "bearer",
                "expires_at": expires,
            },
        )
        resp.set_cookie(
            key="everlingo_sess",
            value=token,
            httponly=True,
            secure=config.trusted_proxy != "127.0.0.1",
            samesite="lax",
        )
        return resp

    for static_path, media_type in STATIC_MEDIA_TYPES.items():

        @app.get(static_path, include_in_schema=False)
        async def serve_static(path: str = static_path, media_type: str = media_type):
            file = os.path.join(_static_dir(), path.lstrip("/"))
            if not os.path.exists(file):
                return JSONResponse(
                    content={"message": "Frontend not built. Run `npm run build` in the web/ directory."},
                    status_code=503,
                )
            if static_path == "/manifest.webmanifest":
                return _static_response(file, media_type=media_type, cache=MANIFEST_CACHE_CONTROL)
            return _static_response(file, media_type=media_type, cache=ASSET_CACHE_CONTROL)

    @app.get("/logout")
    async def get_logout(request: Request):
        resp = RedirectResponse(url="/login", status_code=302)
        resp.delete_cookie("everlingo_sess", path="/")
        return resp

    @app.get("/me")
    async def get_me(request: Request):
        state: AppState = request.app.state.state
        user_id = request.state.user_id

        cached = state.me_cache.get(user_id)
        if cached:
            return JSONResponse(content=cached)

        user_info = await state.master.get_user(user_id)
        if user_info is None:
            return JSONResponse(
                content={"error": {"code": "user_not_found", "message": "User not found"}},
                status_code=404,
            )

        result = {
            "user_id": user_info.user_id,
            "user_name": user_info.user_name,
            "display_name": user_info.display_name,
        }
        state.me_cache.set(user_id, result)
        return JSONResponse(content=result)

    @app.get("/healthz")
    async def healthz(request: Request):
        return JSONResponse(content={"status": "ok"})

    @app.get("/self-service")
    async def get_self_service(request: Request):
        index = os.path.join(_static_dir(), "self-service.html")
        if not os.path.exists(index):
            return JSONResponse(
                content={"message": "Frontend not built. Run `npm run build` in the web/ directory."},
                status_code=503,
            )
        return _static_response(index)

    @app.get("/self-service/pat")
    async def get_self_service_pat(request: Request):
        index = os.path.join(_static_dir(), "pat.html")
        if not os.path.exists(index):
            return JSONResponse(
                content={"message": "Frontend not built. Run `npm run build` in the web/ directory."},
                status_code=503,
            )
        return _static_response(index)

    @app.get("/self-service/api/pats")
    async def list_self_service_pats(request: Request):
        state: AppState = request.app.state.state
        user_id = request.state.user_id

        pats = await state.master.pat_list(user_id)
        if pats is None:
            return JSONResponse(
                content={"error": {"code": "pat_list_failed", "message": "Failed to list tokens"}},
                status_code=502,
            )
        return JSONResponse(
            content=[
                {
                    "id": p.id,
                    "label": p.label,
                    "created_at": p.created_at,
                    "last_used_at": p.last_used_at,
                    "expires_at": p.expires_at,
                }
                for p in pats
            ]
        )

    @app.post("/self-service/api/pats")
    async def create_self_service_pat(request: Request):
        state: AppState = request.app.state.state
        user_id = request.state.user_id

        body = await request.json()
        label = body.get("label", "").strip()
        if not label:
            return JSONResponse(
                content={"error": {"code": "invalid_request", "message": "label is required"}},
                status_code=400,
            )

        result = await state.master.pat_create(user_id, label)
        if result is None:
            return JSONResponse(
                content={"error": {"code": "pat_create_failed", "message": "Failed to create token"}},
                status_code=502,
            )
        return JSONResponse(
            content={
                "id": result.id,
                "token": result.token,
                "label": result.label,
                "created_at": result.created_at,
                "expires_at": result.expires_at,
            },
            status_code=201,
        )

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
    async def catch_all(request: Request, path: str):
        state: AppState = request.app.state.state
        user_id = request.state.user_id

        backend_url = await state.resolve_backend(user_id)
        if backend_url is None:
            return JSONResponse(
                content={"error": {"code": "backend_unavailable", "message": "Backend is not available"}},
                status_code=503,
            )

        return await proxy_request(request, backend_url, state.proxy_client)

    return app


def run_daemon(config_path: str) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = RouterConfig.load(config_path)
    app = create_app(config)

    host, port_str = config.listen.split(":")
    port = int(port_str)

    logger.info("Starting WS-Router on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")
