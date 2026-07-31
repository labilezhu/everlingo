# ref: docs/impl-spec/workspace-console/architecture.md — 状态机与 IPC 协议
# 线程安全状态机。WeChatBot SDK 回调来自 bot 线程（写入方），
# admin server 读取来自 uvicorn 线程（读取方）。
#
# state 取值（无 error 态；错误由 GET /last_error 独立提供）：
#   starting / waiting_scan / scanned / logined
# 关键转移：logined → waiting_scan（session expired 重登重新触发 on_qr_url）。

from __future__ import annotations

import threading
from datetime import datetime, timezone

VALID_STATES = ("starting", "waiting_scan", "scanned", "logined")


class WechatAdminState:
    """Wechat channel 的 admin 状态。线程安全。"""

    def __init__(self, state: str = "starting") -> None:
        if state not in VALID_STATES:
            raise ValueError(f"invalid state: {state}")
        self._lock = threading.Lock()
        self._state: str = state
        self._qr_url: str | None = None
        self._last_error: str | None = None
        self._last_error_at: str | None = None

    # ── 写入方（SDK 回调 / 登录包装）────────────────────────────

    def set_state(self, state: str) -> None:
        """设置 state。"""
        if state not in VALID_STATES:
            raise ValueError(f"invalid state: {state}")
        with self._lock:
            self._state = state

    def set_qr_url(self, qr_url: str | None) -> None:
        """设置当前 QR-Code 网页 URL；None 清除（如登录成功后）。"""
        with self._lock:
            self._qr_url = qr_url

    def set_last_error(self, err: BaseException) -> None:
        """记录最近一次错误（不改 state；错误可能是瞬时的）。"""
        with self._lock:
            self._last_error = str(err)
            self._last_error_at = datetime.now(timezone.utc).isoformat()

    # SDK 回调映射（ref: channel-wechat-ilink.md — WeChatBot 回调）

    def on_qr_url(self, url: str) -> None:
        """on_qr_url：新 QR 就绪，进入等待扫码。"""
        with self._lock:
            self._state = "waiting_scan"
            self._qr_url = url

    def on_scanned(self) -> None:
        """on_scanned：用户已扫码，等待手机端确认。"""
        with self._lock:
            self._state = "scanned"

    def on_expired(self) -> None:
        """on_expired：QR 过期，SDK 将请求新 QR（等 on_qr_url）。"""
        with self._lock:
            self._state = "waiting_scan"

    # ── 读取方（admin server）────────────────────────────────────

    def snapshot(self) -> dict:
        """返回当前状态快照（dict）。"""
        with self._lock:
            return {
                "state": self._state,
                "qr_url": self._qr_url,
                "last_error": self._last_error,
                "last_error_at": self._last_error_at,
            }
