from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from everlingo.gateway.channels.envelope import UserInputEnvelope


@dataclass
class ChannelMetadata:
    name: str
    supported_sound_media_format: list[str] = field(default_factory=list)
    channel_prompt: str = ""


class Channel(ABC):
    """Channel 抽象基类。

    ref: gateway.md — Channel
    ref: ADR 20260719 — 使用 recv_envelope 替代 recv
    所有 channel 子类必须实现 recv_envelope。
    """

    @abstractmethod
    async def init(self) -> None:
        pass

    @abstractmethod
    async def send_typing_hint(self) -> None:
        pass

    @abstractmethod
    async def stop_typing_hint(self) -> None:
        pass

    @abstractmethod
    async def send(self, content: str) -> None:
        pass

    @abstractmethod
    async def recv_envelope(self) -> UserInputEnvelope | None:
        """读取一条用户输入，以结构化 envelope 返回；None 表示 channel 结束。"""
        pass

    async def send_sound(self, content: bytes, format: str) -> None:
        """默认不支持声音；子类按需覆盖。"""
        return

    def get_metadata(self) -> ChannelMetadata:
        """默认无声音能力、空 prompt；子类按需覆盖。"""
        return ChannelMetadata(name=type(self).__name__)
