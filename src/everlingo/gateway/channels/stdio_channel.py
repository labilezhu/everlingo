# ref: channel-stdio.md — Stdio Channel 实现
# send 输出到 stdout，recv_envelope 阻塞读取 stdin 一行。
# /quit 命令或 EOF/KeyboardInterrupt 时返回 None，Session 据此退出循环。


import asyncio

from everlingo.gateway.channels.channel import Channel
from everlingo.gateway.channels.envelope import UserInputEnvelope, wrap_plain_text


class StdioChannel(Channel):
    """Stdio Channel 实现。
    
    ref: /docs/impl-spec/channel-stdio.md
    ref: ADR 20260719 — 使用 recv_envelope 替代 recv
    - send: 输出到 stdout，消息内容后加换行符
    - recv_envelope: 读取 stdin 一行并包装为 envelope；收到 /quit、EOF 或 KeyboardInterrupt 时返回 None
    """

    async def init(self) -> None:
        """初始化 Channel，打印欢迎信息。"""
        print("\n=== EverLingo 依娃外教 ===")
        print("输入你想查的单词或需要翻译的文本。")
        print("输入 /quit 退出。")

    async def send_typing_hint(self) -> None:
        """
        发送 “正在打字提示” 给对方
        """
        pass
    async def stop_typing_hint(self) -> None:
        """
        发送 “打字已停止提示” 给对方
        """
        pass

    async def send(self, content: str) -> None:
        """输出消息到 stdout。
        
        Args:
            content: 消息内容
        """
        print(f"\n{content}\n")

    async def recv_envelope(self) -> UserInputEnvelope | None:
        """阻塞读取 stdin 一行，包装为 UserInputEnvelope。
        
        Returns:
            包装后的 envelope；若用户输入 /quit、触发 EOF 或 KeyboardInterrupt 则返回 None
        """
        try:
            line = (await asyncio.to_thread(input, "\n> ")).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            return None

        if line.lower() == "/quit":
            print("再见！")
            return None

        if not line:
            return await self.recv_envelope()
        return wrap_plain_text(line)
