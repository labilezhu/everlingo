from typing import Protocol

class Channel(Protocol):
    def send(self, message: str):
        """
        输出消息到 channel 。

        Args:
            message: 消息
        """        
        pass
    def recv(self) -> str:
        """
        从 channel 阻塞读取消息。如果当前无消息，会 block 到有消息或 Channel 结果后返回。

        Returns:
            消息。如果 Channel 结束了，返回 None
        """           
        pass