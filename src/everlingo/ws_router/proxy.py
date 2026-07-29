"""反向代理模块 — httpx 反代 + SSE 流式透传。

ref: ws-router.md §3.3 (4)
"""

from __future__ import annotations

import logging
from typing import Callable

import httpx
from fastapi import Request, Response
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-authenticate",
    "proxy-authorization", "te", "trailers",
    "transfer-encoding", "upgrade",
})

REMOVE_HEADERS = frozenset({"cookie", "authorization", "host", "content-length"})


def _filter_headers(headers) -> dict[str, str]:
    result = {}
    for key, value in headers.items():
        lower = key.lower()
        if lower in HOP_BY_HOP or lower in REMOVE_HEADERS:
            continue
        result[key] = value
    return result


async def proxy_request(
    request: Request,
    backend_url: str,
    client: httpx.AsyncClient,
) -> Response:
    path = request.url.path
    query = request.url.query
    target = f"{backend_url.rstrip('/')}{path}"
    if query:
        target += f"?{query}"

    headers = _filter_headers(request.headers)
    headers["X-Everlingo-User"] = request.state.user_id

    body = await request.body()

    is_sse = request.headers.get("accept") == "text/event-stream"

    if is_sse:
        return await _proxy_sse(client, target, request.method, headers, body)
    return await _proxy_regular(client, target, request.method, headers, body)


def _filter_response_headers(headers) -> dict[str, str]:
    return {
        k: v for k, v in headers.items()
        if k.lower() not in {"content-encoding", "content-length", "transfer-encoding"}
    }


async def _proxy_regular(
    client: httpx.AsyncClient,
    target: str,
    method: str,
    headers: dict[str, str],
    body: bytes,
) -> StreamingResponse:
    req = client.build_request(method, target, headers=headers, content=body or None)
    resp = await client.send(req, stream=True)
    status = resp.status_code
    out_headers = _filter_response_headers(resp.headers)

    async def iterate():
        async for chunk in resp.aiter_bytes():
            yield chunk

    return StreamingResponse(iterate(), status_code=status, headers=out_headers)


async def _proxy_sse(
    client: httpx.AsyncClient,
    target: str,
    method: str,
    headers: dict[str, str],
    body: bytes,
) -> StreamingResponse:
    req = client.build_request(method, target, headers=headers, content=body or None)
    resp = await client.send(req, stream=True)
    status = resp.status_code
    out_headers = _filter_response_headers(resp.headers)

    async def event_stream():
        async for line in resp.aiter_lines():
            yield f"{line}\n"

    return StreamingResponse(
        event_stream(),
        status_code=status,
        media_type="text/event-stream",
        headers=out_headers,
    )
