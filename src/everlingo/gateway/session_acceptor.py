# ref: session-acceptor.md — Session Acceptor 创建 Channel 并向 Gateway 提交 session 创建请求

import asyncio
import logging
import uuid
from typing import Any, Protocol

from .channels.channel import Channel
from .channels.stdio_channel import StdioChannel
from .channels.wechat_channel import WechatChannel
from .wechat_admin.lifecycle import LockAcquireError, acquire_lock, write_pid
from .wechat_admin.server import AdminServer, admin_socket_path, create_admin_app


logger = logging.getLogger(__name__)


class SessionAcceptor(Protocol):
    """Session Acceptor 协议。

    ref: /docs/impl-spec/session-acceptor.md
    负责创建 Channel，生成 session_id，向 Gateway 提交 session 创建请求。
    不负责创建 Session 对象。
    """

    async def start(self, gateway: Any) -> asyncio.Task:
        """启动 acceptor，返回需要等待的 task。

        Args:
            gateway: 实现了 accept_session(channel, session_id) 的对象

        Returns:
            asyncio.Task: 需要等待的 task（session task 或 server task）
        """
        ...


class StdioSessionAcceptor(SessionAcceptor):
    """Stdio Session Acceptor。

    ref: /docs/impl-spec/session-acceptor.md — Stdio Session Acceptor
    启动时立即创建一个 Stdio Channel。不支持 session resume。
    """

    async def start(self, gateway: Any) -> asyncio.Task:
        channel = StdioChannel()
        session_id = str(uuid.uuid4())
        return await gateway.accept_session(channel, session_id)


class WechatSessionAcceptor(SessionAcceptor):
    """Wechat Session Acceptor。

    ref: /docs/impl-spec/session-acceptor.md — Wechat Session Acceptor
    ref: docs/impl-spec/workspace-console/architecture.md — 单例与生命周期
    启动时：
    - acquire_lock() 获取单例锁（另一个 wechat gateway 在跑则抛 LockAcquireError）
    - write_pid() 写 pid 文件
    - 创建 Wechat Channel + Session，并行启动 UDS admin server
    - 当 bot 线程结束（/shutdown 或崩溃）时关闭 admin server 并退出进程

    不支持 session resume。
    """

    def __init__(self) -> None:
        self._lock_fd: int | None = None

    async def start(self, gateway: Any) -> asyncio.Task:
        self._lock_fd = acquire_lock()
        write_pid()

        channel = WechatChannel()
        session_id = str(uuid.uuid4())
        session_task = await gateway.accept_session(channel, session_id)

        app = create_admin_app(channel.admin_state, channel.request_stop)
        admin = AdminServer(app, admin_socket_path())
        admin_task = asyncio.create_task(admin.run())

        async def _run_until_bot_done() -> None:
            """等待进程退出条件后收尾。

            - /shutdown 或 bot 崩溃 → bot 线程结束 → 关 admin server
            - 外部 SIGINT/SIGTERM → uvicorn 捕获 → admin server 先退出
            """
            bot_done = asyncio.create_task(
                asyncio.to_thread(channel.wait_run_done)
            )
            done, _ = await asyncio.wait(
                {bot_done, admin_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if admin_task in done and bot_done not in done:
                # 外部信号（SIGINT/SIGTERM）：uvicorn 已收尾；
                # 停 bot（结束 wait_run_done 线程）+ 取消 session，让进程退出
                session_task.cancel()
                channel.request_stop()
                await asyncio.gather(bot_done, return_exceptions=True)
            else:
                # bot 结束（/shutdown 或崩溃）：关 admin server
                admin.request_shutdown()
            await asyncio.gather(admin_task, session_task, return_exceptions=True)

        return asyncio.create_task(_run_until_bot_done())
