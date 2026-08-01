# ref: docs/impl-spec/workspace-console/ws-console-arch.md — WechatRuntime 与生命周期管理
# WechatRuntime：wechat channel 的 in-process 托管者。
# - 实现 SessionAcceptor 协议（start -> supervisor task），由 Gateway 调度
#   （无参 config-driven / --channel_wechat / --channel_web 均经此路径）。
# - 同时是 web console 的控制句柄（start_wechat / stop_wechat / status）。
# - on_logined 回调持久化 enable=true；stop 持久化 enable=false（重启自动恢复）。

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any, Callable, Optional

from everlingo.gateway.channels.wechat_channel import WechatChannel
from everlingo.gateway.session_acceptor import SessionAcceptor
from everlingo.gateway.wechat_admin.lifecycle import LockAcquireError, acquire_lock

logger = logging.getLogger(__name__)

# 优雅停止 bot 的超时（秒）。超时后放弃等待（bot 线程为 daemon，不阻塞进程退出）。
STOP_TIMEOUT = 10.0


def _save_enable(enable: bool) -> None:
    """写 everlingo.yaml 的 plugins.channels.channel_wechat.enable。

    ref: workspace-console/ws-console-arch.md §7.3 enable 写入时机汇总
    """
    from everlingo import setting

    s = setting.load_setting()
    s.plugins.channels.channel_wechat.enable = enable
    setting.save_setting(s)
    logger.info("saved channel_wechat.enable=%s to everlingo.yaml", enable)


class WechatRuntime(SessionAcceptor):
    """Wechat channel 的 in-process 托管者。

    Args:
        auto_start: 启动时（gateway 无参 config-driven enable / --channel_wechat）
            是否自动 start_wechat。False 表示 idle，等 console 手动启动。
        on_bot_exit: bot 线程结束（崩溃 / 外部 stop）时的回调。standalone
            模式由 gateway 注入以退出进程；web 托管模式不注入（进程继续跑）。
    """

    def __init__(
        self,
        auto_start: bool = False,
        on_bot_exit: Optional[Callable[[], None]] = None,
    ) -> None:
        self._auto_start = auto_start
        self._on_bot_exit = on_bot_exit
        self._gateway: Any = None
        self._channel: Optional[WechatChannel] = None
        self._session_id: Optional[str] = None
        self._lock_fd: Optional[int] = None
        self._started = False
        self._conflict = False
        self._stop_event = asyncio.Event()
        self._bot_watch_task: Optional[asyncio.Task] = None

    @property
    def channel(self) -> Optional[WechatChannel]:
        return self._channel

    # ── SessionAcceptor ─────────────────────────────────────────

    async def start(self, gateway: Any) -> asyncio.Task:
        """启动托管。若 auto_start 则自动 start_wechat；返回 supervisor task。

        supervisor task 驻留至 gateway shutdown（request_shutdown），wechat
        被 stop 后保持 idle 等待再次 start，不触发进程退出。
        """
        self._gateway = gateway
        if self._auto_start:
            await self.start_wechat()
        return asyncio.create_task(self._supervise())

    async def _supervise(self) -> None:
        """gateway shutdown（stop_event）时优雅停 wechat 并退出。"""
        await self._stop_event.wait()
        await self.stop_wechat(no_persist=True)

    def request_shutdown(self) -> None:
        """gateway 触发 shutdown（SIGINT / 其它 acceptor 结束）时调用。"""
        self._stop_event.set()

    # ── console 控制接口 ────────────────────────────────────────

    async def start_wechat(self) -> dict:
        """启动 wechat（幂等：已运行返回当前状态；锁冲突返回 conflict）。"""
        if self._channel is not None and self._started:
            return self.status()

        self._conflict = False
        try:
            self._lock_fd = acquire_lock()
        except LockAcquireError as e:
            self._conflict = True
            logger.warning("wechat start conflict: %s", e)
            return self.status()

        channel = WechatChannel(on_logined=self._on_logined)
        await channel.init()
        self._channel = channel
        self._session_id = str(uuid.uuid4())
        await self._gateway.accept_session(channel, self._session_id)
        self._started = True
        self._bot_watch_task = asyncio.create_task(self._watch_bot())
        logger.info("wechat channel started (session=%s)", self._session_id)
        return self.status()

    async def stop_wechat(self, no_persist: bool = False) -> dict:
        """停止 wechat：request_stop → 等 bot 退出 → 释放锁。

        Args:
            no_persist: True 时不写 enable=false（gateway shutdown 场景，
                非用户主动停止，保持 enable 供下次重启自动恢复）。
        """
        channel = self._channel
        if channel is None:
            self._started = False
            return self.status()

        logger.info("stopping wechat channel...")
        channel.request_stop()
        try:
            await asyncio.wait_for(
                asyncio.to_thread(channel.wait_run_done), timeout=STOP_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning("wechat bot stop timeout after %.0fs", STOP_TIMEOUT)
        await self._cleanup()
        self._started = False
        self._conflict = False
        if not no_persist:
            _save_enable(False)
        return self.status()

    def status(self) -> dict:
        """综合状态：SDK 四态（starting/waiting_scan/scanned/logined）
        + runtime 综合态（stopped / conflict）。

        ref: workspace-console/ws-console-arch.md §3.1
        """
        if self._conflict:
            return {
                "running": False,
                "state": "conflict",
                "qr_url": None,
                "last_error": None,
            }
        if self._channel is None or not self._started:
            return {
                "running": False,
                "state": "stopped",
                "qr_url": None,
                "last_error": None,
            }
        snap = self._channel.admin_state.snapshot()
        return {
            "running": True,
            "state": snap["state"],
            "qr_url": snap["qr_url"],
            "last_error": snap["last_error"],
        }

    # ── 内部 ─────────────────────────────────────────────────────

    async def _watch_bot(self) -> None:
        """监控 bot 线程：结束时（崩溃 / 外部 stop）自动清理，回到 idle。"""
        channel = self._channel
        if channel is None:
            return
        await asyncio.to_thread(channel.wait_run_done)
        await self._cleanup()
        self._started = False
        logger.info("wechat bot thread ended, channel idle")
        if self._on_bot_exit is not None:
            self._on_bot_exit()

    async def _cleanup(self) -> None:
        """幂等清理：释放锁、清 channel 引用（session 经 gateway done callback 移除）。"""
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None
        self._channel = None
        self._session_id = None

    def _on_logined(self) -> None:
        """登录成功（首登或 session-expired 重登）→ 持久化 enable=true。"""
        _save_enable(True)
