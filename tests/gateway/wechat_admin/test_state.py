"""
WechatAdminState 状态机单测。

ref: TEST_STYLE.md — 只测核心流程和状态转移
ref: docs/impl-spec/workspace-console/architecture.md — 状态机
"""
import pytest

from everlingo.gateway.wechat_admin.state import WechatAdminState


class TestWechatAdminStateInit:
    def test_default_state_is_starting(self):
        state = WechatAdminState()
        assert state.snapshot()["state"] == "starting"

    def test_invalid_initial_state_raises(self):
        with pytest.raises(ValueError, match="invalid state"):
            WechatAdminState(state="bogus")

    def test_invalid_set_state_raises(self):
        state = WechatAdminState()
        with pytest.raises(ValueError, match="invalid state"):
            state.set_state("bogus")


class TestWechatAdminStateCallbacks:
    """SDK 回调 → 状态转移。ref: architecture.md — 状态转移"""

    def test_on_qr_url_sets_waiting_scan_with_url(self):
        state = WechatAdminState()
        state.on_qr_url("https://example.com/qr1")
        snap = state.snapshot()
        assert snap["state"] == "waiting_scan"
        assert snap["qr_url"] == "https://example.com/qr1"

    def test_on_scanned_sets_scanned(self):
        state = WechatAdminState(state="waiting_scan")
        state.on_scanned()
        assert state.snapshot()["state"] == "scanned"

    def test_on_expired_returns_to_waiting_scan(self):
        state = WechatAdminState(state="scanned")
        state.on_expired()
        assert state.snapshot()["state"] == "waiting_scan"

    def test_login_success_sets_logined_and_clears_qr(self):
        state = WechatAdminState(state="scanned")
        state.set_state("logined")
        state.set_qr_url(None)
        snap = state.snapshot()
        assert snap["state"] == "logined"
        assert snap["qr_url"] is None


class TestWechatAdminStateError:
    """错误记录：不改 state，独立提供。ref: architecture.md — 无 error 态"""

    def test_set_last_error_keeps_state(self):
        state = WechatAdminState(state="waiting_scan")
        state.set_last_error(ValueError("boom"))
        snap = state.snapshot()
        assert snap["state"] == "waiting_scan"
        assert snap["last_error"] == "boom"
        assert snap["last_error_at"] is not None

    def test_no_error_returns_empty(self):
        state = WechatAdminState()
        snap = state.snapshot()
        assert snap["last_error"] is None
        assert snap["last_error_at"] is None


class TestWechatAdminStateRelogin:
    """logined → waiting_scan 重登回退。ref: architecture.md — 关键转移规则"""

    def test_logined_then_expired_qr_returns_to_waiting_scan(self):
        state = WechatAdminState(state="logined")
        state.on_qr_url("https://example.com/qr-new")
        snap = state.snapshot()
        assert snap["state"] == "waiting_scan"
        assert snap["qr_url"] == "https://example.com/qr-new"
