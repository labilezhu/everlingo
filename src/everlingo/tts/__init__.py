from typing import Protocol


class TTSError(Exception):
    """TTS 合成失败时抛出。"""
    pass


class TTSProvider(Protocol):
    """TTS 提供者协议。"""
    async def synthesize(self, text: str, fmt: str = "mp3") -> bytes:
        """合成语音。

        Args:
            text: 要合成的文本
            fmt: 输出格式，默认 "mp3"

        Returns:
            合成的音频字节

        Raises:
            TTSError: 合成失败时
        """
        ...


def get_tts_provider() -> TTSProvider:
    """获取 TTS 提供者。当前固定返回 EdgeTTSProvider。"""
    from .edge_tts import EdgeTTSProvider
    return EdgeTTSProvider()
