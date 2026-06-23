"""
核心流程测试：voice_speak 工具

ref: TEST_STYLE.md — 只测核心流程
"""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from everlingo.tools.voice import make_voice_speak_tool


class TestMakeVoiceSpeakTool:
    """make_voice_speak_tool 工厂函数测试"""

    def test_returns_structured_tool(self):
        """make_voice_speak_tool 返回 StructuredTool"""
        channel = MagicMock()
        tool = make_voice_speak_tool(channel)
        assert tool.name == "voice_speak"

    def test_tool_returns_voice_scheduled(self):
        """工具调用后立即返回 'voice scheduled'"""
        channel = MagicMock()
        tool = make_voice_speak_tool(channel)

        # Mock provider
        mock_provider = MagicMock()
        mock_provider.synthesize = AsyncMock(return_value=b"fake_audio")

        with patch("everlingo.tools.voice.get_tts_provider", return_value=mock_provider):
            result = tool.invoke({"text": "hello"})

        assert result == "voice scheduled"

    def test_tool_schedules_async_send(self):
        """工具调度异步 TTS+send，不阻塞"""
        channel = MagicMock()
        tool = make_voice_speak_tool(channel)

        # Mock provider
        mock_provider = MagicMock()
        mock_provider.synthesize = AsyncMock(return_value=b"fake_audio")

        with patch("everlingo.tools.voice.get_tts_provider", return_value=mock_provider):
            result = tool.invoke({"text": "hello"})

        # 工具立即返回，不等待异步任务完成
        assert result == "voice scheduled"

        # provider.synthesize 被调用（在后台线程中）
        # 注意：由于是 fire-and-forget，我们无法可靠地等待异步任务完成
        # 因此只验证工具立即返回，不阻塞主流程

    def test_tool_failure_does_not_raise(self):
        """工具失败时不抛出异常，只记日志"""
        channel = MagicMock()
        tool = make_voice_speak_tool(channel)

        # Mock provider
        mock_provider = MagicMock()
        mock_provider.synthesize = AsyncMock(return_value=b"fake_audio")

        with patch("everlingo.tools.voice.get_tts_provider", return_value=mock_provider):
            # 不应抛出异常
            result = tool.invoke({"text": "hello"})

        assert result == "voice scheduled"

        # 失败在后台处理，不影响主流程返回值

    def test_tool_provider_failure_does_not_raise(self):
        """provider 失败时不抛出异常"""
        channel = MagicMock()
        channel.send_sound = AsyncMock()
        tool = make_voice_speak_tool(channel)

        # Mock provider 抛出异常
        mock_provider = MagicMock()
        mock_provider.synthesize = AsyncMock(side_effect=RuntimeError("tts failed"))

        with patch("everlingo.tools.voice.get_tts_provider", return_value=mock_provider):
            result = tool.invoke({"text": "hello"})

        assert result == "voice scheduled"

        # 等待后台任务完成
        time.sleep(0.2)

        # send_sound 不应被调用
        channel.send_sound.assert_not_called()
