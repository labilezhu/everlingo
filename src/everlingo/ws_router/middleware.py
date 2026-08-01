"""WS-Router 中间件：trusted_proxy、auth_middleware。

ref: ws-router.md §3.3
"""

from __future__ import annotations

import hashlib
import logging
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from .auth import verify_session_token
from .cache import TTLCache
from .master_client import MasterClient, UserInfo

logger = logging.getLogger(__name__)

WHITELIST_PATHS = {"/login", "/logout", "/healthz"}
STATIC_WHITELIST_PREFIXES = ("/login", "/static", "/assets", "/favicon.png", "/manifest.webmanifest", "/icon-")


async def trusted_proxy_middleware(request: Request, call_next: Callable) -> Response:
    if request.url.path == "/login":
        response = await call_next(request)
        return response
    response = await call_next(request)
    return response


def make_auth_middleware(
    jwt_secret: str,
    master: MasterClient,
    pat_cache: TTLCache,
    session_ttl: int,
) -> Callable:
    async def auth_middleware(request: Request, call_next: Callable) -> Response:
        if request.url.path in WHITELIST_PATHS or request.url.path.startswith(STATIC_WHITELIST_PREFIXES):
            return await call_next(request)

        user_id = None
        user_name = None

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            payload = verify_session_token(token, jwt_secret)
            if payload:
                user_id = payload.get("sub")
                user_name = payload.get("user_name")
            else:
                result = await _verify_pat(token, master, pat_cache)
                if result:
                    user_id = result.user_id
                    user_name = result.user_name

        if not user_id:
            cookie = request.cookies.get("everlingo_sess")
            if cookie:
                payload = verify_session_token(cookie, jwt_secret)
                if payload:
                    user_id = payload.get("sub")
                    user_name = payload.get("user_name")

        if user_id:
            request.state.user_id = user_id
            request.state.user_name = user_name
            return await call_next(request)

        accept = request.headers.get("Accept", "")
        if "text/html" in accept:
            return RedirectResponse(url="/login", status_code=302)
        return JSONResponse(
            content={"error": {"code": "unauthorized", "message": "Authentication required"}},
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer realm="everlingo"'},
        )

    return auth_middleware


async def _verify_pat(token: str, master: MasterClient, cache: TTLCache) -> UserInfo | None:
    key = hashlib.sha256(token.encode()).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return cached
    result = await master.pat_verify(token)
    if result:
        cache.set(key, result)
    return result
