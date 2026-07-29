"""WS-Router 反代测试：httpx.MockTransport 模拟后端 ws-container。

覆盖：普通请求透传、SSE 流式透传、hop-by-hop 头剔除、X-Everlingo-User 注入
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from everlingo.ws_router.app import create_app
from everlingo.ws_router.auth import create_session_token
from everlingo.ws_router.config import RouterConfig
from everlingo.ws_router.master_client import BackendInfo, UserInfo


def _make_mock_transport(backend_url: str):
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host and request.url.port
        assert request.headers.get("X-Everlingo-User") is not None
        assert request.headers.get("cookie") is None
        assert request.headers.get("authorization") is None

        if "events" in str(request.url):
            async def sse_body():
                yield b"data: hello\n\n"
                yield b"data: world\n\n"
            return httpx.Response(200, text="data: hello\n\ndata: world\n\n",
                                  headers={"Content-Type": "text/event-stream"})

        body = await request.aread()
        return httpx.Response(
            200,
            json={"method": request.method, "path": str(request.url), "body": body.decode() if body else None},
        )

    return httpx.MockTransport(handler)


@pytest.fixture
def config() -> RouterConfig:
    return RouterConfig(
        jwt_secret="test-jwt-secret",
        master_secret="test-master-secret",
        master_url="http://localhost:8101",
    )


@pytest.fixture
def client(config: RouterConfig):
    app = create_app(config)
    app.state.state.master.authenticate = AsyncMock(
        return_value=UserInfo(user_id="uid-1", user_name="mark", display_name="Mark")
    )
    app.state.state.master.get_default_backend = AsyncMock(
        return_value=BackendInfo(
            ws_container_id="ws-1",
            backend_url="http://backend:8000",
            status="started",
        )
    )
    mock_transport = _make_mock_transport("http://backend:8000")
    app.state.state.proxy_client = httpx.AsyncClient(transport=mock_transport)
    with TestClient(app) as c:
        yield c


class TestProxy:
    def test_regular_proxy(self, client):
        token = create_session_token("uid-1", "mark", "test-jwt-secret", 3600)
        resp = client.get(
            "/api/session/test-123",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_proxy_injects_user_header(self, client):
        token = create_session_token("uid-1", "mark", "test-jwt-secret", 3600)
        resp = client.post(
            "/api/session",
            json={"msg": "hello"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_proxy_strips_cookie(self, client):
        token = create_session_token("uid-1", "mark", "test-jwt-secret", 3600)
        client.cookies.set("everlingo_sess", token)
        resp = client.get("/api/session/x")
        assert resp.status_code == 200

    def test_backend_unavailable_503(self, client):
        app = client.app
        app.state.state.master.get_default_backend = AsyncMock(return_value=None)
        token = create_session_token("uid-1", "mark", "test-jwt-secret", 3600)
        resp = client.get("/api/session/x", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 503
        assert "backend_unavailable" in resp.text

    def test_backend_url_cached(self, client):
        app = client.app
        token = create_session_token("uid-1", "mark", "test-jwt-secret", 3600)
        client.get("/api/session/x", headers={"Authorization": f"Bearer {token}"})
        assert app.state.state.master.get_default_backend.call_count == 1
        client.get("/api/session/y", headers={"Authorization": f"Bearer {token}"})
        assert app.state.state.master.get_default_backend.call_count == 1
