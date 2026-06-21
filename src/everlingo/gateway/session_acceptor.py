# ref: session-acceptor.md — Session Acceptor 创建 Channel 并向 Gateway 提交 session 创建请求

import uuid
from typing import Any, Protocol

from .channels.channel import Channel
from .channels.stdio_channel import StdioChannel
from .channels.wechat_channel import WechatChannel


class SessionAcceptor(Protocol):
    """Session Acceptor 协议。

    ref: /docs/impl-spec/session-acceptor.md
    负责创建 Channel，生成 session_id，向 Gateway 提交 session 创建请求。
    不负责创建 Session 对象。
    """

    async def accept(self, gateway: Any) -> None:
        """向 gateway 提交 session 创建请求。

        Args:
            gateway: 实现了 accept_session(channel, session_id) 的对象
        """
        ...


class StdioSessionAcceptor:
    """Stdio Session Acceptor。

    ref: /docs/impl-spec/session-acceptor.md — Stdio Session Acceptor
    启动时立即创建一个 Stdio Channel。不支持 session resume。
    """

    async def accept(self, gateway: Any) -> None:
        channel = StdioChannel()
        session_id = str(uuid.uuid4())
        await gateway.accept_session(channel, session_id)


class WechatSessionAcceptor:
    """Wechat Session Acceptor。

    ref: /docs/impl-spec/session-acceptor.md — Wechat Session Acceptor
    启动时立即创建一个 Wechat Channel。不支持 session resume。
    """

    async def accept(self, gateway: Any) -> None:
        channel = WechatChannel()
        session_id = str(uuid.uuid4())
        await gateway.accept_session(channel, session_id)
