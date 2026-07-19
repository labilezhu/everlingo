"""
核心流程测试：WechatChannel

ref: TEST_STYLE.md — 只测核心流程和用户输入边缘情况
ref: channel-wechat-ilink.md — 单元测试时只能 Mock wechatbot-sdk
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from everlingo import workspace
from everlingo.gateway.channels.wechat_channel import WechatChannel


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

    def test_init_starts_bot_run_in_daemon_thread(self, isolated_workspace):
        """init() 在独立 daemon 线程中启动 bot.run()。"""
        mock_wechatbot_class, mock_thread_class, mock_bot = self._patched_init()
        with patch("everlingo.gateway.channels.wechat_channel.WeChatBot", mock_wechatbot_class), \
             patch("threading.Thread", mock_thread_class) as MockThread:
            mock_thread_instance = MagicMock()
            MockThread.return_value = mock_thread_instance

            channel = WechatChannel()
            asyncio.run(channel.init())

        mock_thread_class.assert_called_once_with(target=mock_bot.run, daemon=True)
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
        channel._queue.put("你好")

        result = asyncio.run(channel.recv_envelope())
        assert result is not None
        assert result.chat.message == "你好"

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

        # 模拟收到消息
        mock_msg = MagicMock()
        mock_msg.user_id = "user_abc@im.wechat"
        mock_msg.text = "学习英语"

        asyncio.run(registered_callback(mock_msg))

        assert channel._last_user_id == "user_abc@im.wechat"
        assert channel._queue.get_nowait() == "学习英语"


class TestWechatChannelMetadata:
    """ref: channel-wechat-ilink.md — get_metadata"""

    def test_get_metadata_returns_channel_name(self, isolated_workspace):
        """get_metadata() 返回 WechatChannel 名称和默认值。"""
        channel = WechatChannel()
        metadata = channel.get_metadata()
        assert metadata.name == "WechatChannel"