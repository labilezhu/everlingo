from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ChannelMetadata:
    name: str
    supported_sound_media_format: list[str] = field(default_factory=list)
    channel_prompt: str = ""


class Channel(Protocol):
    async def init(self):
        pass

    async def send_typing_hint(self) -> None:
        pass

    async def stop_typing_hint(self) -> None:
        pass

    async def send(self, content: str):
        pass

    async def recv(self) -> str | None:
        pass

    async def send_sound(self, content: bytes, format: str) -> None:
        pass

    def get_metadata(self) -> ChannelMetadata:
        return ChannelMetadata(
            name=type(self).__name__,
            supported_sound_media_format=[],
            channel_prompt="当前对话通道(Channel)不支持声音",
        )
