# ref: gateway.md — Session 封装 Channel 实例与 Agent 实例的绑定
# 每个 Session 对象有自己的线程，loop 阻塞读取 channel 的消息。

import asyncio

from .channels.channel import Channel
from ..agents.agent import MainAgent, MessageEvent


class Session:
    """Session 封装 Channel 与 Agent 的绑定，驱动消息循环。

    ref: /docs/impl-spec/gateway.md — Session
    """

    def __init__(self, channel: Channel, agent: MainAgent) -> None:
        self.channel = channel
        self.agent = agent

    async def run(self) -> None:
        """消息循环：阻塞读取 channel 消息，交由 agent 处理，将回复发回 channel。

        ref: /docs/impl-spec/gateway.md — Session
        循环直到 channel.recv() 返回 None（用户输入 /quit 或 EOF）。
        """
        await self.channel.init()

        while True:
            text = await self.channel.recv()
            if text is None:
                break

            input_msg = MessageEvent(text=text)
            await self.channel.send_typing_hint()
            reply = self.agent.invoke(input_msg)
            await self.channel.stop_typing_hint()
            await self.channel.send(reply.text)
