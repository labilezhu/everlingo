"""WS-Router 认证测试：JWT + login 页面。

覆盖：JWT 签发/验签/过期/篡改、GET/POST /login（JSON）、/logout、/me
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

import everlingo.ws_router.app as app_module
from everlingo.ws_router.app import create_app
from everlingo.ws_router.auth import create_session_token, verify_session_token
from everlingo.ws_router.config import RouterConfig
from everlingo.ws_router.master_client import UserInfo


@pytest.fixture
def config() -> RouterConfig:
    return RouterConfig(
        jwt_secret="test-jwt-secret",
        master_secret="test-master-secret",
        master_url="http://localhost:8101",
    )


@pytest.fixture
def app(config: RouterConfig):
    app = create_app(config)
    return app


@pytest.fixture
def client(app, config: RouterConfig):
    app.state.state.master.authenticate = AsyncMock(
        return_value=UserInfo(user_id="uid-1", user_name="mark", display_name="Mark")
    )
    app.state.state.master.get_user = AsyncMock(
        return_value=UserInfo(user_id="uid-1", user_name="mark", display_name="Mark")
    )
    app.state.state.master.get_default_backend = AsyncMock(
        return_value=None
    )
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------


class TestJWT:
    def test_create_and_verify(self):
        token = create_session_token("uid-1", "mark", "secret", 3600)
        payload = verify_session_token(token, "secret")
        assert payload is not None
        assert payload["sub"] == "uid-1"
        assert payload["user_name"] == "mark"
        assert "exp" in payload
        assert "jti" in payload

    def test_verify_expired(self):
        token = create_session_token("uid-1", "mark", "secret", -1)
        payload = verify_session_token(token, "secret")
        assert payload is None

    def test_verify_wrong_secret(self):
        token = create_session_token("uid-1", "mark", "real-secret", 3600)
        payload = verify_session_token(token, "wrong-secret")
        assert payload is None

    def test_verify_tampered(self):
        token = create_session_token("uid-1", "mark", "secret", 3600)
        parts = token.split(".")
        tampered = parts[0] + "." + parts[1] + ".invalidsig"
        payload = verify_session_token(tampered, "secret")
        assert payload is None

    def test_verify_garbage(self):
        payload = verify_session_token("not-a-jwt", "secret")
        assert payload is None


# ---------------------------------------------------------------------------
# Login page
# ---------------------------------------------------------------------------


class TestLoginPage:
    @pytest.fixture
    def static_dist(self, tmp_path, monkeypatch):
        dist = tmp_path / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "assets" / "login.js").write_text("console.log('login')")
        (dist / "login.html").write_text(
            '<!doctype html><html><head><title>Login</title></head><body>'
            '<div id="root"></div><script type="module" src="/assets/login.js"></script>'
            '</body></html>'
        )
        (dist / "favicon.png").write_bytes(b"fake-png")
        (dist / "manifest.webmanifest").write_text('{"name": "login"}')
        monkeypatch.setattr(app_module, "_static_dir", lambda: str(dist))
        return dist

    def test_get_login_returns_html(self, client, static_dist):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")
        assert "Login" in resp.text
        assert "/assets/login.js" in resp.text

    def test_get_login_not_built(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(app_module, "_static_dir", lambda: str(tmp_path / "missing"))
        resp = client.get("/login")
        assert resp.status_code == 503

    def test_assets_served_without_auth(self, client, static_dist):
        resp = client.get("/assets/login.js")
        assert resp.status_code == 200
        assert resp.text == "console.log('login')"

    def test_static_whitelisted_without_auth(self, client, static_dist):
        for path in ("/favicon.png", "/manifest.webmanifest"):
            resp = client.get(path)
            assert resp.status_code == 200

    def test_post_login_json_success(self, client):
        resp = client.post(
            "/login",
            json={"username": "mark", "password": "pass"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "uid-1"
        assert data["token_type"] == "bearer"
        assert "access_token" in data
        assert "everlingo_sess" in resp.cookies

    def test_post_login_json_failure(self, client):
        app = client.app
        app.state.state.master.authenticate = AsyncMock(return_value=None)
        resp = client.post(
            "/login",
            json={"username": "mark", "password": "wrong"},
        )
        assert resp.status_code == 401
        data = resp.json()
        assert data["error"]["code"] == "invalid_credentials"


class TestLogout:
    def test_logout_clears_cookie(self, client):
        token = create_session_token("uid-1", "mark", "test-jwt-secret", 3600)
        client.cookies.set("everlingo_sess", token)
        resp = client.get("/logout", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/login"


class TestMe:
    def test_get_me_authenticated(self, client):
        token = create_session_token("uid-1", "mark", "test-jwt-secret", 3600)
        resp = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_name"] == "mark"
        assert data["display_name"] == "Mark"

    def test_get_me_unauthorized(self, client):
        resp = client.get("/me", follow_redirects=False)
        assert resp.status_code == 401

    def test_get_me_caches(self, client):
        app = client.app
        token = create_session_token("uid-1", "mark", "test-jwt-secret", 3600)
        resp1 = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert resp1.status_code == 200
        assert app.state.state.master.get_user.call_count == 1
        resp2 = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert resp2.status_code == 200
        assert app.state.state.master.get_user.call_count == 1  # cached
