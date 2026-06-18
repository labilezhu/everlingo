# ref: channel-wechat-ilink.md — Wechat Channel 实现
# 使用 wechatbot-sdk 接入微信，收发消息。
# WeChatBot 是长生命单例，bot.run() 在独立线程中阻塞运行。
# recv() 从线程安全的同步 Queue 阻塞读取消息；send() 用保存的 user_id 主动发送。

import queue
import threading
from typing import Optional

from wechatbot import WeChatBot


class WechatChannel:
    """Wechat(微信) 消息 Channel 实现。

    ref: /docs/impl-spec/channel-wechat-ilink.md
    - init: 创建 WeChatBot 单例，注册消息回调，在独立线程启动 bot.run()
    - recv: 从线程安全的同步 Queue 阻塞读取消息，返回消息文字；Channel 结束返回 None
    - send: 使用最近一次保存的 user_id 调用 bot.send() 主动发送消息
    """

    def __init__(self) -> None:
        # WeChatBot 单例，应用生命周期内只创建一次
        self._bot: Optional[WeChatBot] = None
        # 每次收到消息时保存最新的 user_id，用于主动发送消息
        self._last_user_id: Optional[str] = None
        # 线程安全的同步队列：回调将消息放入，recv() 阻塞读取
        # ref: channel-wechat-ilink.md — recv 阻塞读取，bot.run() 在独立线程运行
        self._queue: queue.Queue[Optional[str]] = queue.Queue()

    async def init(self) -> None:
        """初始化 Wechat Channel。

        ref: /docs/impl-spec/channel-wechat-ilink.md
        创建 WeChatBot 单例，注册消息回调，在独立线程启动 bot.run()。
        bot.run() 会在 stdout 输出登录 QR-CODE，提示用户扫码登录。
        """
        self._bot = WeChatBot()

        # 注册消息回调：收到消息时将文字放入队列
        @self._bot.on_message
        async def _handle_message(msg) -> None:
            # ref: channel-wechat-ilink.md — 主动发送消息必须带上之前消息的 user_id
            self._last_user_id = msg.user_id
            # queue.Queue 是线程安全的，可从任意线程 put
            self._queue.put(msg.text)

        # bot.run() 会 block 当前线程，因此在独立线程中运行
        # ref: channel-wechat-ilink.md — 在 stdout 中输出登录QR-CODE，block 当前线程，所以必要时需要专用线程
        bot_thread = threading.Thread(target=self._bot.run, daemon=True)
        bot_thread.start()

    def recv(self) -> Optional[str]:
        """阻塞读取微信消息。

        ref: /docs/impl-spec/channel-wechat-ilink.md
        从线程安全的同步 Queue 阻塞读取；返回 None 表示 Channel 结束。
        """
        return self._queue.get()
    
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
