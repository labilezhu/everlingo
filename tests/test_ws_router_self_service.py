"""WS-Router 自服务页面测试：/self-service、/self-service/pat、/self-service/api/pats。

覆盖：HTML 页面服务、认证要求、PAT list/create API。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import everlingo.ws_router.app as app_module
from everlingo.ws_router.app import create_app
from everlingo.ws_router.auth import create_session_token
from everlingo.ws_router.config import RouterConfig
from everlingo.ws_router.master_client import PatCreateResult, PatInfo, UserInfo


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
    app.state.state.master.pat_list = AsyncMock(
        return_value=[
            PatInfo(
                id="pat-1",
                label="chrome_ext",
                created_at="2026-08-01T00:00:00Z",
                last_used_at=None,
                expires_at=None,
            )
        ]
    )
    app.state.state.master.pat_create = AsyncMock(
        return_value=PatCreateResult(
            id="pat-2",
            token="elpat_newtoken123",
            label="vault",
            created_at="2026-08-01T01:00:00Z",
            expires_at=None,
        )
    )
    with TestClient(app) as c:
        yield c


def _auth_headers() -> dict:
    token = create_session_token("uid-1", "mark", "test-jwt-secret", 3600)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def static_dist(tmp_path: Path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "assets" / "self-service.js").write_text("console.log('self-service')")
    (dist / "assets" / "pat.js").write_text("console.log('pat')")
    (dist / "self-service.html").write_text(
        '<!doctype html><html><head><title>Self Service</title></head><body>'
        '<div id="root"></div><script type="module" src="/assets/self-service.js"></script>'
        '</body></html>'
    )
    (dist / "pat.html").write_text(
        '<!doctype html><html><head><title>PAT</title></head><body>'
        '<div id="root"></div><script type="module" src="/assets/pat.js"></script>'
        '</body></html>'
    )
    monkeypatch.setattr(app_module, "_static_dir", lambda: str(dist))
    return dist


class TestSelfServicePage:
    def test_get_self_service_authenticated(self, client, static_dist):
        resp = client.get("/self-service", headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")
        assert "Self Service" in resp.text

    def test_get_self_service_pat_authenticated(self, client, static_dist):
        resp = client.get("/self-service/pat", headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")
        assert "PAT" in resp.text

    def test_get_self_service_requires_auth(self, client, static_dist):
        resp = client.get("/self-service", follow_redirects=False)
        assert resp.status_code == 401

    def test_get_self_service_browser_redirects_login(self, client, static_dist):
        resp = client.get("/self-service", headers={"Accept": "text/html"}, follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/login"

    def test_get_self_service_not_built(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(app_module, "_static_dir", lambda: str(tmp_path / "missing"))
        resp = client.get("/self-service", headers=_auth_headers())
        assert resp.status_code == 503


class TestSelfServicePatApi:
    def test_list_pats(self, client, static_dist):
        resp = client.get("/self-service/api/pats", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["label"] == "chrome_ext"
        assert "token" not in data[0]

    def test_create_pat(self, client, static_dist):
        resp = client.post(
            "/self-service/api/pats",
            json={"label": "vault"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["token"] == "elpat_newtoken123"
        assert data["label"] == "vault"
        client.app.state.state.master.pat_create.assert_awaited_once_with("uid-1", "vault")

    def test_create_pat_missing_label(self, client, static_dist):
        resp = client.post(
            "/self-service/api/pats",
            json={"label": "  "},
            headers=_auth_headers(),
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "invalid_request"

    def test_api_requires_auth(self, client, static_dist):
        resp = client.get("/self-service/api/pats")
        assert resp.status_code == 401

    def test_create_pat_unauthenticated(self, client, static_dist):
        resp = client.post(
            "/self-service/api/pats",
            json={"label": "vault"},
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 401
