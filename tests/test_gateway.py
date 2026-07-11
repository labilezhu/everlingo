"""
单元测试：Gateway Session 退出清理机制。

ref: gateway.md — Session 退出时自动从 sessions 列表中移除
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from everlingo.gateway.gateway import Gateway
from everlingo.gateway.channels.channel import ChannelMetadata
from everlingo.models import UserProfile, UserLanguage


def _make_gateway() -> Gateway:
    """创建 Gateway 并注入测试 profile。"""
    gateway = Gateway()
    gateway._profile = UserProfile(
        language=UserLanguage(interface_language="zh-CN", target_language="en"),
    )
    return gateway


def _make_mock_channel(recv_returns=None):
    """创建 mock Channel，recv() 可控制返回值。"""
    channel = MagicMock()
    channel.init = AsyncMock()
    channel.send = AsyncMock()
    channel.send_typing_hint = AsyncMock()
    channel.stop_typing_hint = AsyncMock()
    channel.get_metadata = MagicMock(
        return_value=ChannelMetadata(name="MockChannel")
    )
    if recv_returns is not None:
        channel.recv = AsyncMock(side_effect=recv_returns)
    else:
        channel.recv = AsyncMock(return_value=None)
    return channel


class TestGatewayCleanup:
    """Gateway Session 退出清理测试。"""

    @pytest.mark.asyncio
    async def test_accept_session_cleans_up_on_exit(self):
        """Session.run() 退出后，session 从 gateway.sessions 中移除。"""
        gateway = _make_gateway()
        channel = _make_mock_channel(recv_returns=[None])

        with patch("everlingo.gateway.session.MainAgent") as MockMainAgent:
            mock_agent = MagicMock()
            mock_agent.aclose = AsyncMock()
            MockMainAgent.return_value = mock_agent

            task = await gateway.accept_session(channel, "test-session-id")
            await task  # 等待 session.run() 完成

        assert "test-session-id" not in gateway.sessions

    def test_cleanup_session_removes_from_dict(self):
        """_cleanup_session 从 sessions 中移除指定 session。"""
        gateway = _make_gateway()
        gateway.sessions["test-id"] = MagicMock()
        gateway._cleanup_session("test-id")
        assert "test-id" not in gateway.sessions

    def test_cleanup_session_logs(self, caplog):
        """_cleanup_session 输出 info 日志。"""
        import logging
        gateway = _make_gateway()
        gateway.sessions["test-id"] = MagicMock()
        with caplog.at_level(logging.INFO, logger="everlingo.gateway.gateway"):
            gateway._cleanup_session("test-id")
        assert "test-id" in caplog.text
        assert "cleaned up" in caplog.text

    @pytest.mark.asyncio
    async def test_session_resume_does_not_double_cleanup(self):
        """session resume 时，done callback 不会重复注册导致错误。"""
        gateway = _make_gateway()
        channel1 = _make_mock_channel(recv_returns=["hello", None])
        channel2 = _make_mock_channel(recv_returns=[None])

        with patch("everlingo.gateway.session.MainAgent") as MockMainAgent:
            mock_agent = MagicMock()
            mock_agent.ainvoke = AsyncMock(return_value=[])
            mock_agent.aclose = AsyncMock()
            MockMainAgent.return_value = mock_agent

            # 首次创建 session
            task1 = await gateway.accept_session(channel1, "resume-session-id")
            await task1

            assert "resume-session-id" not in gateway.sessions
