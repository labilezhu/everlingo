import edge_tts

from . import TTSError


class EdgeTTSProvider:
    """使用 Edge TTS 合成语音。

    ref: tts-spec.md — EdgeTTSProvider
    """

    async def synthesize(self, text: str, fmt: str = "mp3") -> bytes:
        """合成语音。

        使用 edge_tts.Communicate 自动探测语言，流式收集到 bytes。

        Args:
            text: 要合成的文本
            fmt: 输出格式，当前固定 "mp3"

        Returns:
            合成的音频字节

        Raises:
            TTSError: 合成失败时
        """
        if not text.strip():
            raise TTSError("empty text")

        try:
            communicate = edge_tts.Communicate(text)
            audio_data = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data.extend(chunk["data"])
            return bytes(audio_data)
        except Exception as e:
            raise TTSError(f"edge-tts synthesize failed: {e}") from e
