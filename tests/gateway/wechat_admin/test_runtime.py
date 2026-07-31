"""
WechatRuntime 单测：in-process 托管生命周期。

ref: TEST_STYLE.md
ref: docs/impl-spec/workspace-console/architecture.md — WechatRuntime 与生命周期管理
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from everlingo import workspace
from everlingo.gateway.wechat_admin import lifecycle, runtime as runtime_mod
from everlingo.gateway.wechat_admin.runtime import WechatRuntime


@pytest.fixture(autouse=True)
def isolated_workspace(monkeypatch, tmp_path):
    """把 workspace 根重定向到 tmp_path（锁文件落到 tmp）。"""
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    yield tmp_path


def _run(coro):
    return asyncio.run(coro)


def _fake_gateway():
    gw = MagicMock()
    gw.accept_session = AsyncMock(return_value=None)
    return gw


def _channel_mock(state="logined", **kwargs):
    ch = MagicMock()
    ch.init = AsyncMock()
    ch.admin_state = MagicMock()
    ch.admin_state.snapshot.return_value = {
        "state": state,
        "qr_url": None if state != "waiting_scan" else "https://example.com/qr",
        "last_error": None,
        "last_error_at": None,
    }
    return ch


class TestStatus:
    def test_status_stopped_when_not_started(self):
        rt = WechatRuntime()
        status = rt.status()
        assert status == {
            "running": False,
            "state": "stopped",
            "qr_url": None,
            "last_error": None,
        }

    def test_status_after_start_returns_channel_state(self, isolated_workspace):
        rt = WechatRuntime()
        rt._gateway = _fake_gateway()
        with patch("everlingo.gateway.wechat_admin.runtime.WechatChannel", _channel_mock):
            _run(rt.start_wechat())
        status = rt.status()
        assert status["running"] is True
        assert status["state"] == "logined"

    def test_status_conflict_when_lock_held(self, isolated_workspace):
        fd = lifecycle.acquire_lock()
        try:
            rt = WechatRuntime()
            rt._gateway = _fake_gateway()
            _run(rt.start_wechat())
            status = rt.status()
            assert status["running"] is False
            assert status["state"] == "conflict"
        finally:
            import os

            os.close(fd)


class TestStartWechat:
    def test_start_acquires_lock_and_inits_channel(self, isolated_workspace):
        gw = _fake_gateway()
        rt = WechatRuntime()
        rt._gateway = gw
        with patch("everlingo.gateway.wechat_admin.runtime.WechatChannel", _channel_mock):
            _run(rt.start_wechat())
        # 锁被持有、channel init、accept_session 各一次
        assert rt._lock_fd is not None
        rt._channel.init.assert_awaited_once()
        gw.accept_session.assert_awaited_once()
        assert rt._session_id is not None

    def test_start_idempotent(self, isolated_workspace):
        gw = _fake_gateway()
        rt = WechatRuntime()
        rt._gateway = gw
        with patch("everlingo.gateway.wechat_admin.runtime.WechatChannel", _channel_mock):
            _run(rt.start_wechat())
            _run(rt.start_wechat())
        rt._channel.init.assert_awaited_once()
        gw.accept_session.assert_awaited_once()

    def test_start_after_stop_restarts(self, isolated_workspace):
        gw = _fake_gateway()
        rt = WechatRuntime()
        rt._gateway = gw
        with patch("everlingo.gateway.wechat_admin.runtime.WechatChannel", _channel_mock):
            _run(rt.start_wechat())
            _run(rt.stop_wechat())
            _run(rt.start_wechat())
        assert rt.status()["running"] is True
        assert gw.accept_session.await_count == 2

    def test_start_conflict_does_not_raise(self, isolated_workspace):
        fd = lifecycle.acquire_lock()
        try:
            rt = WechatRuntime()
            rt._gateway = _fake_gateway()
            with patch("everlingo.gateway.wechat_admin.runtime.WechatChannel", _channel_mock):
                _run(rt.start_wechat())  # 不应抛 LockAcquireError
            assert rt.status()["state"] == "conflict"
        finally:
            import os

            os.close(fd)


class TestStopWechat:
    def test_stop_writes_enable_false_and_releases_lock(self, isolated_workspace):
        gw = _fake_gateway()
        rt = WechatRuntime()
        rt._gateway = gw
        with patch("everlingo.gateway.wechat_admin.runtime.WechatChannel", _channel_mock), \
             patch.object(runtime_mod, "_save_enable") as mock_save:
            _run(rt.start_wechat())
            lock_fd = rt._lock_fd
            _run(rt.stop_wechat())
        mock_save.assert_called_once_with(False)
        assert rt._lock_fd is None
        # 锁已释放，可再次获取
        lifecycle.acquire_lock()  # 不抛则说明已释放
        assert rt.status()["running"] is False
        assert rt.status()["state"] == "stopped"

    def test_stop_no_persist_skips_save(self, isolated_workspace):
        rt = WechatRuntime()
        rt._gateway = _fake_gateway()
        with patch("everlingo.gateway.wechat_admin.runtime.WechatChannel", _channel_mock), \
             patch.object(runtime_mod, "_save_enable") as mock_save:
            _run(rt.start_wechat())
            _run(rt.stop_wechat(no_persist=True))
        mock_save.assert_not_called()


class TestOnLogined:
    def test_on_logined_saves_enable_true(self):
        rt = WechatRuntime()
        with patch.object(runtime_mod, "_save_enable") as mock_save:
            rt._on_logined()
        mock_save.assert_called_once_with(True)


class TestSuperviseAndBotExit:
    @pytest.mark.asyncio
    async def test_auto_start_inits_channel(self, isolated_workspace):
        gw = _fake_gateway()
        rt = WechatRuntime(auto_start=True)
        with patch("everlingo.gateway.wechat_admin.runtime.WechatChannel", _channel_mock):
            task = await rt.start(gw)
        rt._channel.init.assert_awaited_once()
        assert not task.done()
        rt.request_shutdown()
        await task

    @pytest.mark.asyncio
    async def test_request_shutdown_stops_wechat(self, isolated_workspace):
        gw = _fake_gateway()
        rt = WechatRuntime(auto_start=True)
        rt._gateway = gw
        with patch("everlingo.gateway.wechat_admin.runtime.WechatChannel", _channel_mock), \
             patch.object(runtime_mod, "_save_enable") as mock_save:
            task = await rt.start(gw)
            assert rt.status()["running"] is True
            rt.request_shutdown()
            await task
        assert rt.status()["running"] is False
        assert rt._lock_fd is None
        mock_save.assert_not_called()  # no_persist=True：shutdown 不改 enable

    def test_bot_exit_calls_on_bot_exit(self, isolated_workspace):
        gw = _fake_gateway()
        cb = MagicMock()
        rt = WechatRuntime(on_bot_exit=cb)
        rt._gateway = gw
        with patch("everlingo.gateway.wechat_admin.runtime.WechatChannel", _channel_mock):
            _run(rt.start_wechat())
            _run(rt._watch_bot())
        cb.assert_called_once()
        assert rt.status()["running"] is False
