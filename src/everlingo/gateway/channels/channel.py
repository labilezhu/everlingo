from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Protocol


class Channel(Protocol):
    async def init(self):
        """
        初始化 Channel 。可能会有 login 的过程
        """
        pass

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
    async def send(self, content: str):
        """
        输出消息到 channel 。

        Args:
            content: 消息
        """        
        pass
    
    def recv(self) -> str:
        """
        从 channel 阻塞读取/接收消息。如果当前无消息，会 block 到有消息或 Channel 结果后返回。

        Returns:
            消息。如果 Channel 结束了(应用退出)，返回 None
        """           
        pass