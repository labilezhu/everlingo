"""WS-Router 认证测试：JWT + login 页面。

覆盖：JWT 签发/验签/过期/篡改、GET/POST /login 表单/JSON、/logout、/me
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

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
    def test_get_login_returns_html(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")
        assert "EverLingo" in resp.text
        assert "username" in resp.text.lower()

    def test_post_login_form_success(self, client):
        resp = client.post("/login", data={"username": "mark", "password": "pass"}, follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"
        assert "everlingo_sess" in resp.cookies

    def test_post_login_json_success(self, client):
        resp = client.post(
            "/login",
            json={"username": "mark", "password": "pass"},
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "uid-1"
        assert data["token_type"] == "bearer"
        assert "access_token" in data
        assert "everlingo_sess" in resp.cookies

    def test_post_login_form_failure(self, client):
        app = client.app
        app.state.state.master.authenticate = AsyncMock(return_value=None)
        resp = client.post("/login", data={"username": "mark", "password": "wrong"})
        assert resp.status_code == 401
        assert "Invalid" in resp.text

    def test_post_login_json_failure(self, client):
        app = client.app
        app.state.state.master.authenticate = AsyncMock(return_value=None)
        resp = client.post(
            "/login",
            json={"username": "mark", "password": "wrong"},
            headers={"Accept": "application/json"},
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
