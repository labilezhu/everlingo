import asyncio
import logging
import sys
import threading
from typing import Any

from langchain_core.tools import StructuredTool, tool
from pydantic import BaseModel, Field

from ..tts import get_tts_provider

logger = logging.getLogger("everlingo")

_voice_loop: asyncio.AbstractEventLoop | None = None
_voice_thread: threading.Thread | None = None


def _get_voice_loop() -> asyncio.AbstractEventLoop:
    """获取（懒初始化）专用后台 event loop + 线程。"""
    global _voice_loop, _voice_thread
    if _voice_loop is None:
        _voice_loop = asyncio.new_event_loop()
        _voice_thread = threading.Thread(target=_voice_loop.run_forever, daemon=True)
        _voice_thread.start()
    return _voice_loop


async def _speak_async(channel: Any, text: str) -> None:
    """后台协程：合成语音并发送到 channel。"""
    provider = get_tts_provider()
    audio = await provider.synthesize(text, fmt="mp3")
    await channel.send_sound(audio, "mp3")


class _VoiceSpeakArgs(BaseModel):
    text: str = Field(..., description="要朗读并发送给用户的文本")


def make_voice_speak_tool(channel: Any) -> StructuredTool:
    """工厂函数：创建绑定了 channel 的 voice_speak 工具。

    工具是同步的，内部 fire-and-forget 调度异步 TTS+send 到后台线程。
    失败只记日志 + stderr，不影响主流程。
    """

    @tool("voice_speak", args_schema=_VoiceSpeakArgs)
    def voice_speak(text: str) -> str:
        """向用户发送该段文本的语音朗读。

        仅在以下情况调用：
        - 用户在「个性化偏好设置」中要求发送语音
        - 用户在对话中显式要求发音/朗读/听一下

        朗读内容优先级：
        - 查词时：所查单词的发音
        - 翻译时：目标短句的示范发音
        - 仅当用户显式要求「朗读整段回复」时，才发送整段回复的语音

        此工具是异步的，调用后无需等待。
        """
        loop = _get_voice_loop()
        fut = asyncio.run_coroutine_threadsafe(_speak_async(channel, text), loop)

        def _on_done(f: asyncio.Future) -> None:
            try:
                f.result()
            except Exception as e:
                logger.error("voice_speak failed: %s", e)
                print(f"[voice_speak] error: {e}", file=sys.stderr)

        fut.add_done_callback(_on_done)
        return "voice scheduled"

    return voice_speak
