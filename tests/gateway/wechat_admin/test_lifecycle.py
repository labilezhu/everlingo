"""
WechatAdmin lifecycle 单测：单例锁 + pid 文件。

ref: TEST_STYLE.md
ref: docs/impl-spec/workspace-console/architecture.md — 单例与生命周期
"""
import os

import pytest

from everlingo import workspace
from everlingo.gateway.wechat_admin import lifecycle


@pytest.fixture(autouse=True)
def isolated_workspace(monkeypatch, tmp_path):
    """把 workspace 根重定向到 tmp_path。"""
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    yield tmp_path


class TestAcquireLock:
    def test_acquire_creates_lock_file(self, isolated_workspace):
        fd = lifecycle.acquire_lock()
        try:
            assert lifecycle.lock_path().is_file()
        finally:
            os.close(fd)

    def test_second_acquire_fails(self, isolated_workspace):
        fd1 = lifecycle.acquire_lock()
        try:
            with pytest.raises(lifecycle.LockAcquireError):
                lifecycle.acquire_lock()
        finally:
            os.close(fd1)

    def test_lock_released_after_close(self, isolated_workspace):
        fd1 = lifecycle.acquire_lock()
        os.close(fd1)
        # 释放后可再次获取
        fd2 = lifecycle.acquire_lock()
        os.close(fd2)

    def test_lock_error_message_mentions_path(self, isolated_workspace):
        fd1 = lifecycle.acquire_lock()
        try:
            with pytest.raises(lifecycle.LockAcquireError, match="gateway.lock"):
                lifecycle.acquire_lock()
        finally:
            os.close(fd1)


class TestPid:
    def test_write_pid_creates_file_with_current_pid(self, isolated_workspace):
        lifecycle.write_pid()
        try:
            assert lifecycle.pid_path().is_file()
            assert lifecycle.pid_path().read_text(encoding="utf-8") == str(
                os.getpid()
            )
        finally:
            lifecycle.clear_pid()

    def test_clear_pid_removes_file(self, isolated_workspace):
        lifecycle.write_pid()
        lifecycle.clear_pid()
        assert not lifecycle.pid_path().exists()

    def test_clear_pid_idempotent(self, isolated_workspace):
        lifecycle.clear_pid()  # 不存在也不抛错
        assert not lifecycle.pid_path().exists()
