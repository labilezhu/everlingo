# ref: channel-wechat-ilink.md — Wechat Channel 实现
# 使用 wechatbot-sdk 接入微信，收发消息。
# WeChatBot 是长生命单例；登录 + 长轮询在独立线程运行（替代 bot.run()，
# 以注入 logined 状态，见 workspace-console/ws-console-arch.md）。
# recv() 从线程安全的同步 Queue 阻塞读取消息；send() 用保存的 user_id 主动发送。

import asyncio
import logging
import queue
import threading
from pathlib import Path
from typing import Callable, Optional


from wechatbot import AuthError, WeChatBot

from everlingo import workspace
from everlingo.gateway.channels.channel import Channel, ChannelMetadata
from everlingo.gateway.channels.envelope import UserInputEnvelope, wrap_plain_text
from everlingo.gateway.wechat_admin.state import WechatAdminState


logger = logging.getLogger(__name__)

# 初始登录 QR 连续过期后重试间隔（秒）。SDK 单次 login 在 QR 连续过期 3 次后
# abort（wechatbot/auth.py MAX_QR_REFRESH_COUNT=3），重试重新获取新 QR。
LOGIN_RETRY_INTERVAL = 5.0


class WechatChannel(Channel):
    """Wechat(微信) 消息 Channel 实现。

    ref: /docs/impl-spec/channel-wechat-ilink.md
    ref: ADR 20260719 — 使用 recv_envelope 替代 recv
    ref: docs/impl-spec/workspace-console/ws-console-arch.md — 登录路径改造
    - init: 创建 WeChatBot 单例，注册消息回调，在独立线程启动 _run_thread()
    - recv_envelope: 从线程安全的同步 Queue 读取消息并包装为 envelope；返回 None 表示 Channel 结束
    - send: 使用最近一次保存的 user_id 调用 bot.send() 主动发送消息
    """

    def __init__(self, on_logined: Optional[Callable[[], None]] = None) -> None:
        # 登录成功回调（注入：runtime 持久化 enable=true）。
        # ref: workspace-console/ws-console-arch.md §3.2 on_logined 注入
        self._on_logined = on_logined
        # WeChatBot 单例，应用生命周期内只创建一次
        self._bot: Optional[WeChatBot] = None
        # 每次收到消息时保存最新的 user_id，用于主动发送消息
        self._last_user_id: Optional[str] = None
        # 线程安全的同步队列：回调将消息放入，recv() 阻塞读取
        # ref: channel-wechat-ilink.md — recv 阻塞读取，bot 在独立线程运行
        self._queue: queue.Queue[Optional[str]] = queue.Queue()
        # admin 状态：由 SDK 回调（bot 线程）更新，admin server（uvicorn 线程）读取
        self.admin_state = WechatAdminState(state="starting")
        # 标记 bot 线程结束（shutdown / 崩溃），供 acceptor 据此退出进程
        self._run_done = threading.Event()
        # bot 线程的 asyncio loop 与主协程 task（供跨线程取消）
        self._run_loop: Optional[asyncio.AbstractEventLoop] = None
        self._run_main_task: Optional[asyncio.Task] = None
        # init 幂等守卫：WechatRuntime.start_wechat() 与 Session.run() 都会调 init()，
        # 重复调用会重复创建 WeChatBot + 轮询线程，导致同一消息被多 bot 各自入队（收到两次）。
        # ref: docs/impl-spec/gateway.md — Session.run 对 channel.init 的职责
        self._initialized = False

    def _credentials_path(self) -> Path:
        """返回 SDK 保存用户 credentials 的文件路径。

        ref: /docs/impl-spec/channel-wechat-ilink.md — 指定 sdk 保存用户 credentials 的文件
        路径固定为 $workspace/plugins/channels/wechat_channel/credentials/credentials.json
        """
        return (
            workspace.plugins_dir()
            / "channels"
            / "wechat_channel"
            / "credentials"
            / "credentials.json"
        )

    async def init(self) -> None:
        """初始化 Wechat Channel。

        ref: /docs/impl-spec/channel-wechat-ilink.md
        ref: docs/impl-spec/workspace-console/ws-console-arch.md — 登录路径改造
        创建 WeChatBot 单例（注入 admin 回调），注册消息回调，
        在独立线程运行 _run_thread()（首登 + 长轮询）。

        幂等：重复调用直接返回，避免重复创建 bot 实例 / 轮询线程
        （WechatRuntime.start_wechat 与 Session.run 各调一次，见类注释）。
        """
        if self._initialized:
            return
        self._initialized = True

        # ref: channel-wechat-ilink.md — 指定 sdk 保存用户 credentials 的文件
        # 目录不存在时自动创建；调用 WeChatBot 前完成
        cred_path = self._credentials_path()
        cred_path.parent.mkdir(parents=True, exist_ok=True)

        # 注入 admin 回调：登录过程状态反馈到 WechatAdminState
        self._bot = WeChatBot(
            cred_path=str(cred_path),
            on_qr_url=self.admin_state.on_qr_url,
            on_scanned=self.admin_state.on_scanned,
            on_expired=self.admin_state.on_expired,
            on_error=self.admin_state.set_last_error,
        )

        # 注册消息回调：收到消息时将文字放入队列
        @self._bot.on_message
        async def _handle_message(msg) -> None:
            # ref: channel-wechat-ilink.md — 主动发送消息必须带上之前消息的 user_id
            self._last_user_id = msg.user_id
            # queue.Queue 是线程安全的，可从任意线程 put
            self._queue.put(msg.text)

        # login/start 会 block 当前线程，因此在独立线程中运行
        # ref: channel-wechat-ilink.md — block 当前线程，所以必要时需要专用线程
        bot_thread = threading.Thread(target=self._run_thread, daemon=True)
        bot_thread.start()

    # ── 登录与长轮询（替代 bot.run()，注入 logined 状态） ──────────

    def wait_run_done(self) -> None:
        """阻塞等待 bot 线程结束（shutdown / 崩溃）。供 acceptor 退出进程。"""
        self._run_done.wait()

    def request_stop(self) -> None:
        """请求 bot 优雅停止（/shutdown 回调）。

        bot 尚未创建（init 前）时仅尝试取消主协程。
        - bot.stop()：让 start() 长轮询优雅退出
        - 取消主协程：bot 处于 QR 等待 / get_updates 长轮询时 stop() 不生效，
          用 task.cancel() 跨线程打断，保证进程及时退出
        """
        if self._bot is not None:
            self._bot.stop()
        loop = self._run_loop
        task = self._run_main_task
        if loop is not None and task is not None and not task.done():
            loop.call_soon_threadsafe(task.cancel)

    def _run_thread(self) -> None:
        """bot 线程入口：跑 _run()，结束后置 _run_done。

        显式建 loop + main task，以便 request_stop() 跨线程取消。
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        main_task = loop.create_task(self._run())
        self._run_loop = loop
        self._run_main_task = main_task
        try:
            loop.run_until_complete(main_task)
        except asyncio.CancelledError:
            pass
        except Exception:
            # 非取消异常（如登录网络错误）：记日志而非裸 traceback，
            # 进程仍经 _run_done 走正常收尾（acceptor 关 admin server 退出）
            logger.exception("Wechat bot 线程异常退出")
        finally:
            self._run_loop = None
            self._run_main_task = None
            loop.close()
            self._run_done.set()

    async def _run(self) -> None:
        """首登 + 长轮询。等价于 SDK 的 _run_sync()，但注入 logined 状态。

        ref: docs/impl-spec/workspace-console/ws-console-arch.md — logined 注入
        初始登录 QR 连续过期 3 次（AuthError）时重试获取新 QR，进程驻留
        waiting_scan 直到扫码成功；网络等其它登录错误仍传播（进程退出）。
        """
        try:
            self._wrap_login()
            while True:
                try:
                    await self._bot.login()
                    break
                except AuthError:
                    # SDK 单次 login 在 QR 连续过期后 abort；重新获取新 QR
                    await asyncio.sleep(LOGIN_RETRY_INTERVAL)
            await self._bot.start()
        finally:
            # Channel 结束信号：session 收到 None 后退出（session.py）
            self._queue.put(None)

    def _wrap_login(self) -> None:
        """monkey-patch bot.login 注入 logined / last_error。

        SDK 无 on_logged_in 回调（见 channel-wechat-ilink.md / wechatbot/auth.py），
        通过包装 bot.login 覆盖首登与 start() 内 session-expired 重登两条路径。
        """
        orig = self._bot.login
        state = self.admin_state

        async def wrapped(*args, **kwargs):
            try:
                creds = await orig(*args, **kwargs)
            except Exception as e:
                state.set_last_error(e)
                raise
            state.set_state("logined")
            state.set_qr_url(None)
            if self._on_logined is not None:
                self._on_logined()
            return creds

        self._bot.login = wrapped

    async def recv_envelope(self) -> UserInputEnvelope | None:
        """阻塞读取微信消息，包装为 UserInputEnvelope。

        ref: /docs/impl-spec/channel-wechat-ilink.md
        从线程安全的同步 Queue 阻塞读取；返回 None 表示 Channel 结束。
        """
        text = await asyncio.to_thread(self._queue.get)
        return None if text is None else wrap_plain_text(text)
    
    async def send_typing_hint(self) -> None:
        if self._bot is None:
            raise RuntimeError("WechatChannel 尚未初始化，请先调用 init()")
        if self._last_user_id is None:
            raise RuntimeError("尚未收到任何消息，无法获取 user_id 进行主动发送")        
        await self._bot.send_typing(self._last_user_id)

    async def stop_typing_hint(self) -> None:        
        if self._bot is None:
            raise RuntimeError("WechatChannel 尚未初始化，请先调用 init()")
        if self._last_user_id is None:
            raise RuntimeError("尚未收到任何消息，无法获取 user_id 进行主动发送")        
        await self._bot.stop_typing(self._last_user_id)

    async def send(self, content: str) -> None:
        """主动发送消息给最近一次发消息的用户。

        ref: /docs/impl-spec/channel-wechat-ilink.md
        - 支持 markdown 格式
        - 主动发送消息必须带上之前消息的 user_id

        Args:
            content: 消息内容，支持 markdown 格式
        """
        if self._bot is None:
            raise RuntimeError("WechatChannel 尚未初始化，请先调用 init()")
        if self._last_user_id is None:
            raise RuntimeError("尚未收到任何消息，无法获取 user_id 进行主动发送")
        await self._bot.send(self._last_user_id, content)

    async def send_sound(self, content: bytes, format: str) -> None:
        if self._bot is None:
            raise RuntimeError("WechatChannel 尚未初始化，请先调用 init()")
        if self._last_user_id is None:
            raise RuntimeError("尚未收到任何消息，无法获取 user_id 进行主动发送")
        await self._bot.send(self._last_user_id, {"file": content, "file_name": f"voice.{format}" })        

    def get_metadata(self) -> ChannelMetadata:
        return ChannelMetadata(
            name=type(self).__name__,
            supported_sound_media_format=["wav","mp3"],
            channel_prompt="""微信 Clawbot 对话通道(Channel)，有以下特性
            - 支持发送文本和声音
            - 手机屏幕，不适合展示长内容。一次返回的消息内容要控制字数，一般不超过 500 字。
            微信 Clawbot 对话通道有以下注意事项：
            - 手机屏幕，不适合展示横排的内容。如表格。所以尽量不使用表格，如要使用，也要控制每表格行的长度。
            """,
        )