"""
核心流程测试：WebSessionAcceptor — FastAPI 端点

ref: web-session-acceptor.md — FastAPI 后端
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from everlingo.gateway.web_acceptor import app, _channels, create_session, send_message, MessageBody
from everlingo.gateway.channels.web_channel import WebChannel, SSEEvent


def _make_gateway():
    """创建模拟 Gateway，accept_session 正确存储 session。"""
    gateway = MagicMock()
    gateway.sessions = {}

    async def fake_accept_session(channel, session_id):
        session = MagicMock()
        session.id = session_id
        session.channel = channel
        gateway.sessions[session_id] = session
        # 返回一个不会立即完成的 task，避免 done_callback 立刻触发
        return asyncio.create_task(asyncio.Event().wait())

    gateway.accept_session = AsyncMock(side_effect=fake_accept_session)
    return gateway


@pytest.fixture(autouse=True)
def reset_global_state():
    """每个测试前重置全局状态。"""
    _channels.clear()
    import everlingo.gateway.web_acceptor as wa
    wa._gateway = None
    yield
    _channels.clear()


class TestCreateSession:
    """POST /api/session"""

    def test_creates_session_and_returns_id(self):
        import everlingo.gateway.web_acceptor as wa
        wa._gateway = _make_gateway()

        client = TestClient(app)
        resp = client.post("/api/session")
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert len(data["session_id"]) > 0

    @pytest.mark.asyncio
    async def test_registers_channel_in_global_dict(self):
        import everlingo.gateway.web_acceptor as wa
        wa._gateway = _make_gateway()

        # 直接调用 create_session（不通过 HTTP），避免 TestClient 线程问题
        resp = await create_session()
        session_id = resp["session_id"]
        assert session_id in _channels
        assert isinstance(_channels[session_id], WebChannel)

    def test_calls_gateway_accept_session(self):
        gateway = _make_gateway()
        import everlingo.gateway.web_acceptor as wa
        wa._gateway = gateway

        client = TestClient(app)
        resp = client.post("/api/session")
        session_id = resp.json()["session_id"]

        gateway.accept_session.assert_called_once()
        args = gateway.accept_session.call_args[0]
        assert args[1] == session_id

    def test_registers_session_in_gateway(self):
        gateway = _make_gateway()
        import everlingo.gateway.web_acceptor as wa
        wa._gateway = gateway

        client = TestClient(app)
        resp = client.post("/api/session")
        session_id = resp.json()["session_id"]
        assert session_id in gateway.sessions


class TestSendMessage:
    """POST /api/session/{session_id}/message"""

    @pytest.mark.asyncio
    async def test_message_put_into_channel_queue(self):
        import everlingo.gateway.web_acceptor as wa
        wa._gateway = _make_gateway()

        # 直接调用 create_session 和 send_message
        resp = await create_session()
        session_id = resp["session_id"]

        # 模拟发送消息
        await send_message(session_id, MessageBody(text="你好世界"))

        # 验证消息在队列中
        channel = _channels[session_id]
        msg = await channel.recv()
        assert msg == "你好世界"

    def test_404_for_unknown_session(self):
        client = TestClient(app)
        resp = client.post(
            "/api/session/nonexistent/message",
            json={"text": "hello"},
        )
        assert resp.status_code == 404


class TestSSEEvents:
    """GET /api/session/{session_id}/events"""

    def test_sse_returns_404_for_unknown_session(self):
        client = TestClient(app)
        resp = client.get("/api/session/nonexistent/events")
        assert resp.status_code == 404


class TestWebChannelIntegration:
    """WebChannel 直接集成测试（不经过 HTTP）。"""

    @pytest.mark.asyncio
    async def test_channel_send_pushes_to_sse_queue(self):
        channel = WebChannel()
        q = channel.add_sse_client()
        await channel.send("test message")
        event = await q.get()
        assert event.event_type == "message"
        assert event.data["text"] == "test message"

    @pytest.mark.asyncio
    async def test_channel_typing_hint_pushes_to_sse_queue(self):
        channel = WebChannel()
        q = channel.add_sse_client()
        await channel.send_typing_hint()
        event = await q.get()
        assert event.event_type == "typing_hint"
        assert event.data["typing"] is True

    @pytest.mark.asyncio
    async def test_channel_stop_typing_hint_pushes_to_sse_queue(self):
        channel = WebChannel()
        q = channel.add_sse_client()
        await channel.stop_typing_hint()
        event = await q.get()
        assert event.event_type == "typing_hint"
        assert event.data["typing"] is False

    def test_sse_event_format_message(self):
        event = SSEEvent("message", text="hello", session_id="abc")
        text = event.format_sse()
        assert "event: message" in text
        assert '"text": "hello"' in text
        assert text.endswith("\n\n")
