# ref: docs/impl-spec/workspace-console/architecture.md — 单例与生命周期管理
# wechat gateway 进程内：flock 单例锁 + pid 文件。
# 在 --channel_wechat 分支入口调用；进程退出（含崩溃 / kill）时 flock 自动释放。

from __future__ import annotations

import atexit
import fcntl
import logging
import os
from pathlib import Path

from everlingo import workspace

logger = logging.getLogger(__name__)


class LockAcquireError(RuntimeError):
    """无法获得单例锁（另一个 wechat gateway 进程在运行）。"""


def _channel_dir() -> Path:
    return workspace.plugins_dir() / "channels" / "wechat_channel"


def lock_path() -> Path:
    """单例锁文件路径。"""
    return _channel_dir() / "gateway.lock"


def pid_path() -> Path:
    """pid 文件路径（供 web 侧 stop 降级用）。"""
    return _channel_dir() / "gateway.pid"


def acquire_lock() -> int:
    """获取单例独占锁，失败抛 LockAcquireError。

    fcntl.flock(LOCK_EX|LOCK_NB) 保证同一 workspace 下只有一个 wechat
    gateway 进程。flock 在进程退出（含崩溃 / kill）时自动释放。
    返回持有锁的 fd；调用方须在进程存活期间保持（不关闭）。
    """
    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as e:
        os.close(fd)
        raise LockAcquireError(
            f"another Wechat gateway already running (lock: {path})"
        ) from e
    return fd


def write_pid() -> None:
    """写入当前进程 pid 文件；进程退出时经 atexit 清理。"""
    path = pid_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(os.getpid()), encoding="utf-8")
    atexit.register(clear_pid)


def clear_pid() -> None:
    """删除 pid 文件（幂等，忽略错误）。"""
    try:
        pid_path().unlink(missing_ok=True)
    except OSError:
        pass
