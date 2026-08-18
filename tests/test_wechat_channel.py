"""
核心流程测试：WechatChannel

ref: TEST_STYLE.md — 只测核心流程和用户输入边缘情况
ref: channel-wechat-ilink.md — 单元测试时只能 Mock wechatbot-sdk
"""
import asyncio
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image
from wechatbot import AuthError

from everlingo import workspace
from everlingo.gateway.channels import wechat_channel as wechat_channel_mod
from everlingo.gateway.channels.wechat_channel import WechatChannel, _WechatIncoming
from everlingo.image.image_store import image_store, sha256_of_bytes


@pytest.fixture(autouse=True)
def isolated_workspace(monkeypatch, tmp_path):
    """把 WORKSPACE_ROOT 重定向到 tmp_path，避免测试在真实 ~/.everlingo 创建 credentials 目录。

    ref: channel-wechat-ilink.md — init 自动创建 credentials 目录；测试需隔离。
    """
    monkeypatch.setattr(workspace, "WORKSPACE_ROOT", tmp_path / "workspaces")
    workspace.init_workspace("test_ws")
    yield tmp_path


# ── WechatChannel ─────────────────────────────────────────────────────────────

class TestWechatChannelInit:
    """ref: channel-wechat-ilink.md — init 初始化行为"""

    def _patched_init(self):
        """返回 (WeChatBot mock 类, threading.Thread mock 类, mock bot 实例)。"""
        mock_bot = MagicMock()
        mock_bot.on_message = MagicMock(side_effect=lambda f: f)
        mock_bot.run = MagicMock()
        mock_wechatbot_class = MagicMock(return_value=mock_bot)
        mock_thread_class = MagicMock()
        return mock_wechatbot_class, mock_thread_class, mock_bot

    def test_init_creates_wechatbot_singleton(self, isolated_workspace):
        """init() 创建 WeChatBot 单例。"""
        mock_wechatbot_class, mock_thread_class, _ = self._patched_init()
        with patch("everlingo.gateway.channels.wechat_channel.WeChatBot", mock_wechatbot_class), \
             patch("threading.Thread", mock_thread_class):
            channel = WechatChannel()
            asyncio.run(channel.init())

        mock_wechatbot_class.assert_called_once()

    def test_init_starts_login_in_daemon_thread(self, isolated_workspace):
        """init() 在独立 daemon 线程中运行 _run_thread()（首登 + 长轮询）。

        ref: docs/impl-spec/workspace-console/ws-console-arch.md — 登录路径改造
        """
        mock_wechatbot_class, mock_thread_class, _ = self._patched_init()
        with patch("everlingo.gateway.channels.wechat_channel.WeChatBot", mock_wechatbot_class), \
             patch("threading.Thread", mock_thread_class) as MockThread:
            mock_thread_instance = MagicMock()
            MockThread.return_value = mock_thread_instance

            channel = WechatChannel()
            asyncio.run(channel.init())

        # 线程 target 应为 channel._run_thread（替代 SDK 的 bot.run）
        _, kwargs = mock_thread_class.call_args
        assert kwargs["daemon"] is True
        assert callable(kwargs["target"])
        assert kwargs["target"].__self__ is channel
        mock_thread_instance.start.assert_called_once()

    def test_init_creates_credentials_directory(self, isolated_workspace):
        """init() 自动创建 $ws/plugins/channels/wechat_channel/credentials 目录。

        ref: channel-wechat-ilink.md — 如果目录不存在，需要在调用 WeChatBot() 前自动创建。
        """
        cred_dir = (
            isolated_workspace
            / "workspaces"
            / "test_ws"
            / "plugins"
            / "channels"
            / "wechat_channel"
            / "credentials"
        )
        # 调用前目录应不存在
        assert not cred_dir.exists()

        mock_wechatbot_class, mock_thread_class, _ = self._patched_init()
        with patch("everlingo.gateway.channels.wechat_channel.WeChatBot", mock_wechatbot_class), \
             patch("threading.Thread", mock_thread_class):
            channel = WechatChannel()
            asyncio.run(channel.init())

        # 调用后目录被自动创建
        assert cred_dir.is_dir()

    def test_init_passes_cred_path_to_wechatbot(self, isolated_workspace):
        """init() 把 $ws/plugins/channels/wechat_channel/credentials/credentials.json 传给 WeChatBot。"""
        expected_cred_path = (
            isolated_workspace
            / "workspaces"
            / "test_ws"
            / "plugins"
            / "channels"
            / "wechat_channel"
            / "credentials"
            / "credentials.json"
        )

        mock_wechatbot_class, mock_thread_class, _ = self._patched_init()
        with patch("everlingo.gateway.channels.wechat_channel.WeChatBot", mock_wechatbot_class), \
             patch("threading.Thread", mock_thread_class):
            channel = WechatChannel()
            asyncio.run(channel.init())

        mock_wechatbot_class.assert_called_once()
        kwargs = mock_wechatbot_class.call_args.kwargs
        assert kwargs["cred_path"] == str(expected_cred_path)

    def test_init_is_idempotent(self, isolated_workspace):
        """init() 幂等：重复调用不再创建 bot / 轮询线程。

        ref: 回归 — WechatRuntime.start_wechat() 与 Session.run() 各调一次
        channel.init()，重复 init 会创建第二个 WeChatBot + 长轮询线程，
        同一消息被两个 bot 各自入队，导致 Chat Agent 收到两次。
        """
        mock_wechatbot_class, mock_thread_class, _ = self._patched_init()
        with patch("everlingo.gateway.channels.wechat_channel.WeChatBot", mock_wechatbot_class), \
             patch("threading.Thread", mock_thread_class):
            channel = WechatChannel()
            asyncio.run(channel.init())
            asyncio.run(channel.init())

        mock_wechatbot_class.assert_called_once()
        mock_thread_class.assert_called_once()


class TestWechatChannelRecv:
    """ref: channel-wechat-ilink.md — recv 从队列读取消息"""

    def _make_initialized_channel(self, isolated_workspace) -> WechatChannel:
        """创建已初始化的 WechatChannel，bot 不真正启动。"""
        mock_bot = MagicMock()
        mock_bot.on_message = MagicMock(side_effect=lambda f: f)
        mock_bot.run = MagicMock()

        with patch("everlingo.gateway.channels.wechat_channel.WeChatBot", return_value=mock_bot), \
             patch("threading.Thread"):
            channel = WechatChannel()
            asyncio.run(channel.init())

        return channel

    def test_recv_envelope_returns_message_from_queue(self, isolated_workspace):
        """recv_envelope() 从队列中读取并返回包装后的 envelope。"""
        channel = self._make_initialized_channel(isolated_workspace)
        channel._queue.put(_WechatIncoming(text="你好", image_bytes=[]))

        result = asyncio.run(channel.recv_envelope())
        assert result is not None
        assert result.chat.message == "你好"
        assert result.chat.attachments == []

    def test_recv_envelope_returns_none_when_channel_closed(self, isolated_workspace):
        """recv_envelope() 收到 None 时（Channel 结束信号）返回 None。"""
        channel = self._make_initialized_channel(isolated_workspace)
        channel._queue.put(None)

        result = asyncio.run(channel.recv_envelope())
        assert result is None


class TestWechatChannelSend:
    """ref: channel-wechat-ilink.md — send 使用 user_id 主动发送消息"""

    def _make_initialized_channel(self, isolated_workspace) -> tuple[WechatChannel, MagicMock]:
        """创建已初始化的 WechatChannel，返回 channel 和 mock_bot。"""
        mock_bot = MagicMock()
        mock_bot.on_message = MagicMock(side_effect=lambda f: f)
        mock_bot.run = MagicMock()
        mock_bot.send = AsyncMock()

        with patch("everlingo.gateway.channels.wechat_channel.WeChatBot", return_value=mock_bot), \
             patch("threading.Thread"):
            channel = WechatChannel()
            asyncio.run(channel.init())

        return channel, mock_bot

    def test_send_uses_last_user_id(self, isolated_workspace):
        """send() 使用最近一次保存的 user_id 发送消息。"""
        channel, mock_bot = self._make_initialized_channel(isolated_workspace)
        channel._last_user_id = "user_001@im.wechat"

        asyncio.run(channel.send("**你好** world"))

        mock_bot.send.assert_called_once_with("user_001@im.wechat", "**你好** world")

    def test_send_raises_if_not_initialized(self, isolated_workspace):
        """send() 在未初始化时抛出 RuntimeError。"""
        channel = WechatChannel()
        with pytest.raises(RuntimeError, match="尚未初始化"):
            asyncio.run(channel.send("hello"))

    def test_send_raises_if_no_user_id(self, isolated_workspace):
        """send() 在尚未收到任何消息时（无 user_id）抛出 RuntimeError。"""
        channel, _ = self._make_initialized_channel(isolated_workspace)
        # _last_user_id 为 None（尚未收到消息）
        with pytest.raises(RuntimeError, match="user_id"):
            asyncio.run(channel.send("hello"))


class TestWechatChannelMessageCallback:
    """ref: channel-wechat-ilink.md — 消息回调保存 user_id 并放入队列"""

    def test_message_callback_saves_user_id_and_enqueues_text(self, isolated_workspace):
        """收到消息时，回调保存 user_id 并将消息文字放入队列。"""
        registered_callback = None

        def capture_on_message(func):
            nonlocal registered_callback
            registered_callback = func
            return func

        mock_bot = MagicMock()
        mock_bot.on_message = MagicMock(side_effect=capture_on_message)
        mock_bot.run = MagicMock()

        with patch("everlingo.gateway.channels.wechat_channel.WeChatBot", return_value=mock_bot), \
             patch("threading.Thread"):
            channel = WechatChannel()
            asyncio.run(channel.init())

        assert registered_callback is not None

        # 模拟收到消息（SDK IncomingMessage.images 恒为 list）
        mock_msg = MagicMock()
        mock_msg.user_id = "user_abc@im.wechat"
        mock_msg.text = "学习英语"
        mock_msg.images = []

        asyncio.run(registered_callback(mock_msg))

        assert channel._last_user_id == "user_abc@im.wechat"
        incoming = channel._queue.get_nowait()
        assert isinstance(incoming, _WechatIncoming)
        assert incoming.text == "学习英语"
        assert incoming.image_bytes == []


class TestWechatChannelImages:
    """ref: docs/ADR/20260818-image-chat-wechat.md — 微信图片接收 + LLM 分析

    A2 拆分：CDN 下载在 bot 线程回调（_handle_message）完成并携带原始字节入队；
    嗅探/落盘/构造 envelope/eager_warm 在 Session loop 的 _build_envelope_from_message 完成。
    单测 Mock bot：download_raw 返回固定字节，验证入队字节、envelope attachment、
    ImageStore 落盘、eager_warm 调度，以及失败降级（纯图回提示 / 有字丢图）。
    """

    def _make_png(self, color=(40, 80, 120)) -> bytes:
        buf = BytesIO()
        Image.new("RGB", (32, 32), color).save(buf, format="PNG")
        return buf.getvalue()

    def _make_channel_with_bot(self, bot=None):
        channel = WechatChannel(session_id="sess-img")
        if bot is None:
            bot = MagicMock()
            bot.download_raw = AsyncMock()
            bot.send = AsyncMock()
        channel._bot = bot
        channel._last_user_id = "user_img@im.wechat"
        return channel, bot

    def _make_callback_channel(self, bot):
        """通过 init() 注册 on_message 回调，返回 (channel, callback)。"""
        registered_callback = None

        def capture_on_message(func):
            nonlocal registered_callback
            registered_callback = func
            return func

        bot.on_message = MagicMock(side_effect=capture_on_message)
        bot.run = MagicMock()
        with patch("everlingo.gateway.channels.wechat_channel.WeChatBot", return_value=bot), \
             patch("threading.Thread"):
            channel = WechatChannel()
            asyncio.run(channel.init())
        return channel, registered_callback

    @staticmethod
    def _drain_tasks():
        """等 fire-and-forget 的 eager_warm 任务执行完。"""

        async def drain():
            pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        asyncio.run(drain())

    # ── 回调下载（bot 线程） ─────────────────────────────────

    def test_callback_downloads_image_into_queue(self, isolated_workspace):
        """回调下载图片字节并放入队列（_WechatIncoming.image_bytes）。"""
        png = self._make_png(color=(1, 50, 90))
        bot = MagicMock()
        bot.download_raw = AsyncMock(return_value=png)
        channel, callback = self._make_callback_channel(bot)

        mock_msg = MagicMock()
        mock_msg.user_id = "user_img@im.wechat"
        mock_msg.text = "看下这题"
        mock_msg.images = [MagicMock(media="m1", aes_key=None)]

        asyncio.run(callback(mock_msg))

        assert channel._last_user_id == "user_img@im.wechat"
        incoming = channel._queue.get_nowait()
        assert isinstance(incoming, _WechatIncoming)
        assert incoming.text == "看下这题"
        assert incoming.image_bytes == [png]

    def test_callback_downloads_only_first_image(self, isolated_workspace):
        """多图：回调只下载第一张，忽略其余（ADR §32 每消息最多 1 张图）。"""
        png1 = self._make_png(color=(2, 60, 100))
        png2 = self._make_png(color=(3, 70, 110))
        bot = MagicMock()
        bot.download_raw = AsyncMock(side_effect=[png1, png2])
        channel, callback = self._make_callback_channel(bot)

        mock_msg = MagicMock()
        mock_msg.user_id = "user_img@im.wechat"
        mock_msg.text = ""
        mock_msg.images = [
            MagicMock(media="m1", aes_key=None),
            MagicMock(media="m2", aes_key=None),
        ]

        asyncio.run(callback(mock_msg))

        incoming = channel._queue.get_nowait()
        assert incoming.image_bytes == [png1]
        assert bot.download_raw.await_count == 1

    def test_callback_download_failure_enqueues_no_bytes(self, isolated_workspace):
        """回调下载失败：入队空 image_bytes（Session loop 兜底降级）。"""
        bot = MagicMock()
        bot.download_raw = AsyncMock(side_effect=RuntimeError("cdn down"))
        channel, callback = self._make_callback_channel(bot)

        mock_msg = MagicMock()
        mock_msg.user_id = "user_img@im.wechat"
        mock_msg.text = "分析一下"
        mock_msg.images = [MagicMock(media="m1", aes_key=None)]

        asyncio.run(callback(mock_msg))

        incoming = channel._queue.get_nowait()
        assert incoming.text == "分析一下"
        assert incoming.image_bytes == []

    # ── 落盘 / envelope / 预热（Session loop） ──────────────

    def test_image_message_creates_attachment_and_warms(self, isolated_workspace):
        """图片成功：attachment 引用 src_sha；ImageStore 落盘；eager_warm 被调度。"""
        png = self._make_png(color=(10, 20, 30))
        src_sha = sha256_of_bytes(png)
        channel, bot = self._make_channel_with_bot()

        async def run():
            return await channel._build_envelope_from_message(
                _WechatIncoming(text="", image_bytes=[png])
            )

        env = asyncio.run(run())
        self._drain_tasks()

        assert len(env.chat.attachments) == 1
        assert env.chat.attachments[0].src_resource_sha256 == src_sha
        asset = image_store.get(src_sha)
        assert asset is not None
        assert asset.mime_type == "image/png"
        assert asset.storage_key.startswith("session://sess-img/")

    def test_image_message_warms_vision_cache(self, isolated_workspace):
        """图片成功：调度 eager_warm（fire-and-forget）预热 Vision 缓存。"""
        png = self._make_png(color=(11, 22, 33))
        src_sha = sha256_of_bytes(png)
        channel, bot = self._make_channel_with_bot()

        with patch.object(wechat_channel_mod, "eager_warm", new=AsyncMock()) as mock_warm:
            async def run():
                await channel._build_envelope_from_message(
                    _WechatIncoming(text="", image_bytes=[png])
                )

            asyncio.run(run())
            self._drain_tasks()

        mock_warm.assert_awaited_once_with(src_sha)

    def test_multiple_bytes_take_first(self, isolated_workspace):
        """防御：image_bytes 含多份时只处理第一份。"""
        png1 = self._make_png(color=(1, 2, 3))
        png2 = self._make_png(color=(4, 5, 6))
        channel, bot = self._make_channel_with_bot()

        async def run():
            return await channel._build_envelope_from_message(
                _WechatIncoming(text="hi", image_bytes=[png1, png2])
            )

        env = asyncio.run(run())

        assert len(env.chat.attachments) == 1
        assert env.chat.attachments[0].src_resource_sha256 == sha256_of_bytes(png1)
        assert env.chat.message == "hi"

    def test_pure_image_failure_replies_friendly(self, isolated_workspace):
        """纯图失败（无字节 / 格式不支持）：不生成空 turn，回友好提示。"""
        for image_bytes in ([], [b"not an image"]):
            channel, bot = self._make_channel_with_bot()

            async def run():
                return await channel._build_envelope_from_message(
                    _WechatIncoming(text="", image_bytes=image_bytes)
                )

            env = asyncio.run(run())

            assert env.chat.attachments == []
            assert env.chat.message == ""
            bot.send.assert_awaited_once_with(
                "user_img@im.wechat", "暂时无法识别这张图片，请稍后再试或换个角度重新拍摄"
            )
            bot.send.reset_mock()

    def test_failure_with_text_keeps_text(self, isolated_workspace):
        """失败但有文字：丢图保留文字，不额外提示。"""
        channel, bot = self._make_channel_with_bot()

        async def run():
            return await channel._build_envelope_from_message(
                _WechatIncoming(text="分析一下", image_bytes=[])
            )

        env = asyncio.run(run())

        assert env.chat.message == "分析一下"
        assert env.chat.attachments == []
        bot.send.assert_not_awaited()

    def test_unsupported_format_does_not_store(self, isolated_workspace):
        """非图片字节：MIME 嗅探失败，不落盘。"""
        channel, bot = self._make_channel_with_bot()

        async def run():
            return await channel._build_envelope_from_message(
                _WechatIncoming(text="", image_bytes=[b"not an image"])
            )

        asyncio.run(run())

        assert image_store.get(sha256_of_bytes(b"not an image")) is None


class TestWechatChannelAdminState:
    """ref: docs/impl-spec/workspace-console/ws-console-arch.md — 状态机与回调注入"""

    def test_init_injects_admin_callbacks(self, isolated_workspace):
        """init() 把 SDK 回调注入 WechatAdminState。"""
        mock_bot = MagicMock()
        mock_bot.on_message = MagicMock(side_effect=lambda f: f)

        with patch("everlingo.gateway.channels.wechat_channel.WeChatBot", return_value=mock_bot) as MockBot, \
             patch("threading.Thread"):
            channel = WechatChannel()
            asyncio.run(channel.init())

        kwargs = MockBot.call_args.kwargs
        assert kwargs["on_qr_url"] == channel.admin_state.on_qr_url
        assert kwargs["on_scanned"] == channel.admin_state.on_scanned
        assert kwargs["on_expired"] == channel.admin_state.on_expired
        assert kwargs["on_error"] == channel.admin_state.set_last_error

    def test_wrap_login_sets_logined(self, isolated_workspace):
        """包装 bot.login 成功后置 logined 并清 QR。"""
        channel = WechatChannel()
        mock_bot = MagicMock()
        mock_bot.login = AsyncMock(return_value="creds")
        channel._bot = mock_bot

        channel.admin_state.on_qr_url("https://example.com/qr1")
        channel._wrap_login()

        async def run():
            await mock_bot.login()

        asyncio.run(run())
        snap = channel.admin_state.snapshot()
        assert snap["state"] == "logined"
        assert snap["qr_url"] is None

    def test_wrap_login_sets_last_error_on_failure(self, isolated_workspace):
        """包装 bot.login 失败时记 last_error 并重新抛出。"""
        channel = WechatChannel()
        mock_bot = MagicMock()
        mock_bot.login = AsyncMock(side_effect=RuntimeError("net down"))
        channel._bot = mock_bot

        channel._wrap_login()

        async def run():
            await mock_bot.login()

        with pytest.raises(RuntimeError, match="net down"):
            asyncio.run(run())
        assert channel.admin_state.snapshot()["last_error"] == "net down"

    def test_wrap_login_covers_relogin(self, isolated_workspace):
        """start() 内 session-expired 重登（login(force=True)）也经包装置 logined。"""
        channel = WechatChannel()
        mock_bot = MagicMock()
        mock_bot.login = AsyncMock(side_effect=lambda **kw: "creds")
        channel._bot = mock_bot

        channel._wrap_login()

        async def run():
            await mock_bot.login(force=True)

        asyncio.run(run())
        assert channel.admin_state.snapshot()["state"] == "logined"


class TestWechatChannelStop:
    """ref: docs/impl-spec/workspace-console/ws-console-arch.md — 停止语义"""

    def test_request_stop_calls_bot_stop(self, isolated_workspace):
        """request_stop() 调用 bot.stop()。"""
        channel = WechatChannel()
        mock_bot = MagicMock()
        channel._bot = mock_bot
        channel.request_stop()
        mock_bot.stop.assert_called_once()

    def test_request_stop_without_bot_is_safe(self, isolated_workspace):
        """init 前 request_stop() 静默忽略 bot，不报错。"""
        channel = WechatChannel()
        channel.request_stop()  # _bot 为 None

    def test_request_stop_cancels_running_main_task(self, isolated_workspace):
        """QR 等待 / 长轮询阶段 stop() 不生效 → 取消主协程保证及时退出。"""
        channel = WechatChannel()
        channel._bot = MagicMock()

        loop = asyncio.new_event_loop()
        try:
            async def forever():
                await asyncio.sleep(3600)

            main_task = loop.create_task(forever())
            channel._run_loop = loop
            channel._run_main_task = main_task

            channel.request_stop()
            # 让 loop 处理 call_soon_threadsafe 调度的 cancel
            loop.run_until_complete(asyncio.sleep(0))
            with pytest.raises(asyncio.CancelledError):
                loop.run_until_complete(main_task)
            assert main_task.cancelled()
        finally:
            loop.close()


class TestWechatChannelLoginRetry:
    """ref: docs/impl-spec/workspace-console/ws-console-arch.md — 登录重试循环

    SDK 单次 login 在 QR 连续过期 3 次后抛 AuthError abort；初始登录由
    _run() 重试，进程驻留 waiting_scan 直到扫码成功。
    """

    def _make_channel(self, login_side_effect):
        channel = WechatChannel()
        mock_bot = MagicMock()
        login_mock = AsyncMock(side_effect=login_side_effect)
        mock_bot.login = login_mock
        mock_bot.start = AsyncMock()
        channel._bot = mock_bot
        channel._wrap_login()
        return channel, login_mock, mock_bot

    def test_run_retries_login_on_auth_error(self, isolated_workspace):
        """login 抛 AuthError 后重试，成功后进入 start() 并置 logined。"""
        channel, login_mock, mock_bot = self._make_channel(
            [AuthError("QR code expired 3 times — login aborted"), "creds"]
        )
        with patch.object(wechat_channel_mod, "LOGIN_RETRY_INTERVAL", 0):
            asyncio.run(channel._run())

        assert login_mock.await_count == 2
        mock_bot.start.assert_awaited_once()
        assert channel.admin_state.snapshot()["state"] == "logined"
        assert channel.admin_state.snapshot()["qr_url"] is None
        # Channel 结束信号已入队
        assert channel._queue.get_nowait() is None

    def test_run_non_auth_error_propagates(self, isolated_workspace):
        """非 AuthError（如网络错误）仍传播，进程退出。"""
        channel, _, _ = self._make_channel(ValueError("net down"))
        with patch.object(wechat_channel_mod, "LOGIN_RETRY_INTERVAL", 0):
            with pytest.raises(ValueError, match="net down"):
                asyncio.run(channel._run())

    def test_run_thread_logs_and_sets_done_on_exception(self, isolated_workspace):
        """_run_thread 内异常记日志而非裸 traceback，且 _run_done 置位。"""
        channel = WechatChannel()
        channel._bot = MagicMock()

        async def boom():
            raise RuntimeError("boom")

        channel._run = boom
        with patch.object(wechat_channel_mod.logger, "exception") as mock_exc:
            channel._run_thread()
        assert channel._run_done.is_set()
        mock_exc.assert_called_once()

    def test_run_thread_no_log_on_cancel(self, isolated_workspace):
        """正常取消（CancelledError）不记 exception 日志。"""
        channel = WechatChannel()
        channel._bot = MagicMock()

        async def cancelled():
            raise asyncio.CancelledError

        channel._run = cancelled
        with patch.object(wechat_channel_mod.logger, "exception") as mock_exc:
            channel._run_thread()
        mock_exc.assert_not_called()
        assert channel._run_done.is_set()


class TestWechatChannelMetadata:
    """ref: channel-wechat-ilink.md — get_metadata"""

    def test_get_metadata_returns_channel_name(self, isolated_workspace):
        """get_metadata() 返回 WechatChannel 名称和默认值。"""
        channel = WechatChannel()
        metadata = channel.get_metadata()
        assert metadata.name == "WechatChannel"

    def test_get_metadata_supports_image(self, isolated_workspace):
        """get_metadata() 开启 supported_image（注入 analyze_image 等工具）。

        ref: docs/ADR/20260818-image-chat-wechat.md — 决策 8
        """
        channel = WechatChannel()
        assert channel.get_metadata().supported_image is True