"""
核心流程测试：TTS 模块

ref: TEST_STYLE.md — 只测核心流程
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from everlingo.tts import TTSError, get_tts_provider
from everlingo.tts.edge_tts import EdgeTTSProvider


class TestEdgeTTSProvider:
    """EdgeTTSProvider 单元测试"""

    def test_synthesize_returns_bytes(self):
        """synthesize 返回 bytes"""
        provider = EdgeTTSProvider()

        # Mock edge_tts.Communicate
        mock_communicate = MagicMock()
        mock_chunk = {"type": "audio", "data": b"fake_audio_data"}

        async def mock_stream():
            yield mock_chunk

        mock_communicate.stream = mock_stream

        with patch("everlingo.tts.edge_tts.edge_tts.Communicate", return_value=mock_communicate):
            result = asyncio.run(provider.synthesize("hello"))

        assert isinstance(result, bytes)
        assert result == b"fake_audio_data"

    def test_synthesize_empty_text_raises_error(self):
        """空文本抛出 TTSError"""
        provider = EdgeTTSProvider()

        with pytest.raises(TTSError, match="empty text"):
            asyncio.run(provider.synthesize(""))

    def test_synthesize_whitespace_only_raises_error(self):
        """仅空白文本抛出 TTSError"""
        provider = EdgeTTSProvider()

        with pytest.raises(TTSError, match="empty text"):
            asyncio.run(provider.synthesize("   \n\n  "))

    def test_synthesize_failure_raises_tts_error(self):
        """合成失败时抛出 TTSError"""
        provider = EdgeTTSProvider()

        # Mock edge_tts.Communicate 抛出异常
        mock_communicate = MagicMock()

        async def mock_stream():
            raise RuntimeError("network error")
            yield  # Make it a generator

        mock_communicate.stream = mock_stream

        with patch("everlingo.tts.edge_tts.edge_tts.Communicate", return_value=mock_communicate):
            with pytest.raises(TTSError, match="edge-tts synthesize failed"):
                asyncio.run(provider.synthesize("hello"))


class TestGetTTSProvider:
    """get_tts_provider 测试"""

    def test_returns_edge_tts_provider(self):
        """get_tts_provider 返回 EdgeTTSProvider"""
        provider = get_tts_provider()
        assert isinstance(provider, EdgeTTSProvider)
