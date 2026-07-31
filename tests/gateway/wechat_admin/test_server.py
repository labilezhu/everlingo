"""
WechatAdmin server 单测：/status /last_error /shutdown。

ref: TEST_STYLE.md
ref: docs/impl-spec/workspace-console/architecture.md — Admin socket 接口
"""
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from everlingo.gateway.wechat_admin.server import create_admin_app
from everlingo.gateway.wechat_admin.state import WechatAdminState


def _client(state=None, stop_cb=None):
    """构造 TestClient。"""
    app = create_admin_app(state or WechatAdminState(), stop_cb or (lambda: None))
    return TestClient(app)


class TestStatus:
    def test_status_returns_state_and_qr(self):
        state = WechatAdminState(state="waiting_scan")
        state.set_qr_url("https://example.com/qr1")
        client = _client(state=state)
        resp = client.get("/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {
            "state": "waiting_scan",
            "qr_url": "https://example.com/qr1",
        }

    def test_status_logined_qr_is_null(self):
        state = WechatAdminState(state="logined")
        client = _client(state=state)
        body = client.get("/status").json()
        assert body["state"] == "logined"
        assert body["qr_url"] is None


class TestLastError:
    def test_no_error_returns_empty_object(self):
        client = _client()
        resp = client.get("/last_error")
        assert resp.status_code == 200
        assert resp.json() == {}

    def test_error_returns_message_and_at(self):
        state = WechatAdminState()
        state.set_last_error(ValueError("boom"))
        client = _client(state=state)
        body = client.get("/last_error").json()
        assert body["message"] == "boom"
        assert body["at"] is not None


class TestShutdown:
    def test_shutdown_calls_stop_cb(self):
        stop_cb = MagicMock()
        client = _client(stop_cb=stop_cb)
        resp = client.post("/shutdown")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        stop_cb.assert_called_once()

    def test_shutdown_without_stop_cb_returns_ok(self):
        client = _client()
        resp = client.post("/shutdown")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
