# ref: docs/impl-spec/workspace-console/ws-console-arch.md — 单例与生命周期管理
# flock 单例锁：防止 standalone --channel_wechat 与 web 内嵌 wechat 同时跑。
# 锁 fd 由 WechatRuntime 全程持有，进程退出（含崩溃 / kill）时 flock 自动释放。

from __future__ import annotations

import fcntl
import logging
import os
from pathlib import Path

from everlingo import workspace

logger = logging.getLogger(__name__)


class LockAcquireError(RuntimeError):
    """无法获得单例锁（另一个 wechat gateway 在运行）。"""


def _channel_dir() -> Path:
    return workspace.plugins_dir() / "channels" / "wechat_channel"


def lock_path() -> Path:
    """单例锁文件路径。"""
    return _channel_dir() / "gateway.lock"


def acquire_lock() -> int:
    """获取单例独占锁，失败抛 LockAcquireError。

    fcntl.flock(LOCK_EX|LOCK_NB) 保证同一 workspace 下只有一个 wechat
    gateway（standalone 或 web 内嵌）。flock 在进程退出（含崩溃 / kill）时
    自动释放。返回持有锁的 fd；调用方须在持有期间不关闭。
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
