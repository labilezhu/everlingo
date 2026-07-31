"""
Workspace Console router 单测：/api/wechat-channel/{status,start,stop}。

ref: TEST_STYLE.md
ref: docs/impl-spec/workspace-console/architecture.md §5.2 API 端点
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from everlingo.gateway.workspace_console.router import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def fake_runtime():
    rt = MagicMock()
    rt.status.return_value = {
        "running": True,
        "state": "logined",
        "qr_url": None,
        "last_error": None,
    }
    rt.start_wechat = AsyncMock(
        return_value={
            "running": True,
            "state": "waiting_scan",
            "qr_url": "https://example.com/qr",
            "last_error": None,
        }
    )
    rt.stop_wechat = AsyncMock(
        return_value={
            "running": False,
            "state": "stopped",
            "qr_url": None,
            "last_error": None,
        }
    )
    return rt


@pytest.fixture
def fake_gateway(fake_runtime):
    gw = MagicMock()
    gw.wechat_runtime = fake_runtime
    return gw


def _patch_gateway(gw):
    return patch("everlingo.gateway.web_acceptor._gateway", gw)


class TestStatus:
    def test_status_without_gateway_returns_stopped(self, client):
        with _patch_gateway(None):
            resp = client.get("/api/wechat-channel/status")
        assert resp.status_code == 200
        assert resp.json() == {
            "running": False,
            "state": "stopped",
            "qr_url": None,
            "last_error": None,
        }

    def test_status_with_gateway_returns_runtime_status(self, client, fake_gateway, fake_runtime):
        with _patch_gateway(fake_gateway):
            resp = client.get("/api/wechat-channel/status")
        assert resp.status_code == 200
        assert resp.json()["running"] is True
        assert resp.json()["state"] == "logined"
        fake_runtime.status.assert_called_once()


class TestStart:
    def test_start_calls_runtime(self, client, fake_gateway, fake_runtime):
        with _patch_gateway(fake_gateway):
            resp = client.post("/api/wechat-channel/start")
        assert resp.status_code == 200
        assert resp.json()["state"] == "waiting_scan"
        fake_runtime.start_wechat.assert_awaited_once()

    def test_start_without_runtime_returns_503(self, client):
        gw = MagicMock()
        gw.wechat_runtime = None
        with _patch_gateway(gw):
            resp = client.post("/api/wechat-channel/start")
        assert resp.status_code == 503


class TestStop:
    def test_stop_calls_runtime(self, client, fake_gateway, fake_runtime):
        with _patch_gateway(fake_gateway):
            resp = client.post("/api/wechat-channel/stop")
        assert resp.status_code == 200
        assert resp.json()["state"] == "stopped"
        fake_runtime.stop_wechat.assert_awaited_once()

    def test_stop_without_runtime_returns_503(self, client):
        gw = MagicMock()
        gw.wechat_runtime = None
        with _patch_gateway(gw):
            resp = client.post("/api/wechat-channel/stop")
        assert resp.status_code == 503
