"""WS-Router 中间件测试：auth_middleware 路径覆盖 + CORS。

覆盖：JWT / PAT / cookie / 未认证 四条路径 + 浏览器/程序化分流 + CORS 预检
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from everlingo.ws_router.app import create_app
from everlingo.ws_router.auth import create_session_token
from everlingo.ws_router.config import RouterConfig
from everlingo.ws_router.master_client import UserInfo

import everlingo.ws_router.app as app_module


@pytest.fixture
def config() -> RouterConfig:
    return RouterConfig(
        jwt_secret="test-jwt-secret",
        master_secret="test-master-secret",
        master_url="http://localhost:8101",
        cors_allow_origins=["chrome-extension://abc123"],
    )


@pytest.fixture
def client(config: RouterConfig):
    app = create_app(config)
    app.state.state.master.authenticate = AsyncMock(
        return_value=UserInfo(user_id="uid-1", user_name="mark", display_name="Mark")
    )
    app.state.state.master.pat_verify = AsyncMock(
        return_value=UserInfo(user_id="uid-1", user_name="mark", display_name="Mark")
    )
    app.state.state.master.get_default_backend = AsyncMock(return_value=None)
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Auth middleware — authenticated paths
# ---------------------------------------------------------------------------


class TestAuthMiddleware:
    def test_jwt_bearer_authenticated(self, client):
        token = create_session_token("uid-1", "mark", "test-jwt-secret", 3600)
        resp = client.get("/some/protected/path", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 503  # no backend, but auth passed

    def test_pat_bearer_after_jwt_fail(self, client):
        """Invalid JWT → falls back to PAT verify (mocked)."""
        resp = client.get(
            "/some/path",
            headers={"Authorization": "Bearer invalid_jwt"},
        )
        assert resp.status_code == 503

    def test_pat_bearer_cached(self, client):
        app = client.app
        token = create_session_token("uid-1", "mark", "other-secret", 3600)
        resp1 = client.get("/path", headers={"Authorization": f"Bearer {token}"})
        assert resp1.status_code == 503
        # PAT verify should have been called
        pat_call_count = app.state.state.master.pat_verify.call_count
        assert pat_call_count == 1

    def test_cookie_authenticated(self, client):
        token = create_session_token("uid-1", "mark", "test-jwt-secret", 3600)
        client.cookies.set("everlingo_sess", token)
        resp = client.get("/some/path")
        assert resp.status_code == 503

    def test_unauthenticated_browser_redirect(self, client):
        resp = client.get("/some/path", headers={"Accept": "text/html"}, follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/login"

    def test_unauthenticated_programmatic_401(self, client):
        resp = client.get("/some/path", headers={"Accept": "application/json"})
        assert resp.status_code == 401
        data = resp.json()
        assert data["error"]["code"] == "unauthorized"

    def test_unauthenticated_default_401(self, client):
        resp = client.get("/some/path")
        assert resp.status_code == 401
        assert resp.headers.get("www-authenticate") is not None

    def test_whitelist_paths_no_auth(self, client):
        resp = client.get("/healthz")
        assert resp.status_code == 200

    def test_login_path_no_auth(self, client, tmp_path, monkeypatch):
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "login.html").write_text("<!doctype html><title>Login</title>")
        monkeypatch.setattr(app_module, "_static_dir", lambda: str(dist))
        resp = client.get("/login")
        assert resp.status_code == 200

    def test_static_assets_whitelisted_no_auth(self, client, tmp_path, monkeypatch):
        dist = tmp_path / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "assets" / "app.js").write_text("console.log('x')")
        (dist / "favicon.png").write_bytes(b"png")
        (dist / "manifest.webmanifest").write_text('{"name": "app"}')
        monkeypatch.setattr(app_module, "_static_dir", lambda: str(dist))
        for path in ("/assets/app.js", "/favicon.png", "/manifest.webmanifest"):
            resp = client.get(path)
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------


class TestCORS:
    def test_options_preflight(self, client):
        resp = client.options(
            "/some/path",
            headers={
                "Origin": "chrome-extension://abc123",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "chrome-extension://abc123"

    def test_cors_origin_not_allowed(self, client):
        resp = client.get(
            "/some/path",
            headers={"Origin": "https://evil.com"},
        )
        cors_header = resp.headers.get("access-control-allow-origin")
        assert cors_header != "https://evil.com"


class TestCORSRegex:
    """cors_allow_origin_regex 匹配任意 chrome-extension:// origin"""

    @pytest.fixture
    def config(self) -> RouterConfig:
        return RouterConfig(
            jwt_secret="test-jwt-secret",
            master_secret="test-master-secret",
            master_url="http://localhost:8101",
            cors_allow_origin_regex="chrome-extension://.*",
        )

    @pytest.fixture
    def client(self, config: RouterConfig):
        app = create_app(config)
        return TestClient(app)

    def test_regex_matches_extension_origin(self, client):
        resp = client.options(
            "/some/path",
            headers={
                "Origin": "chrome-extension://fahmknjmbjccegjancflflfceobbcmld",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "chrome-extension://fahmknjmbjccegjancflflfceobbcmld"

    def test_regex_rejects_non_chrome_origin(self, client):
        resp = client.options(
            "/some/path",
            headers={
                "Origin": "https://evil.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        cors_header = resp.headers.get("access-control-allow-origin")
        assert cors_header != "https://evil.com"
