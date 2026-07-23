"""
核心流程测试：WebSessionAcceptor — FastAPI 端点

ref: web-session-acceptor.md — FastAPI 后端
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from everlingo.gateway.channels.envelope import UserInputEnvelope
from everlingo.gateway.web_acceptor import app, _channels, create_session, send_message, TextMessageBody
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
        await send_message(session_id, TextMessageBody(text="你好世界"))

        # 验证消息在队列中（envelope 格式）
        channel = _channels[session_id]
        msg = await channel.recv_envelope()
        assert msg is not None
        assert isinstance(msg, UserInputEnvelope)
        assert msg.chat.message == "你好世界"

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


class TestServeEditor:
    """GET /editor, GET /editor/{path}"""

    def test_editor_route_returns_200(self):
        client = TestClient(app)
        resp = client.get("/editor")
        assert resp.status_code == 200
        if "not built" in resp.text.lower():
            data = resp.json()
            assert "not built" in data.get("message", "").lower()
        else:
            assert "小记笔记编辑器" in resp.text

    def test_editor_subpath_returns_200(self):
        client = TestClient(app)
        resp = client.get("/editor/items/vocab/foo.md")
        assert resp.status_code == 200
        if "not built" in resp.text.lower():
            data = resp.json()
            assert "not built" in data.get("message", "").lower()
        else:
            assert "小记笔记编辑器" in resp.text

    def test_editor_routes_registered_before_catch_all(self):
        """/editor 路由应排在 /{path:path} 之前。"""
        paths = [r.path for r in app.routes if hasattr(r, 'path')]
        idx_editor = next(i for i, p in enumerate(paths) if p == "/editor")
        idx_catchall = next(i for i, p in enumerate(paths) if p == "/{path:path}")
        assert idx_editor < idx_catchall

    def test_non_editor_path_does_not_serve_editor_html(self):
        """非 /editor 路径不应重定向到 editor.html。"""
        import os
        client = TestClient(app)
        resp = client.get("/some/random/path")
        assert resp.status_code == 200
        # dist/ 可能存在旧构建产物，所以 text 可能是 HTML 而非 JSON。
        # 核心断言：返回的不是 editor.html 即可。
        text = resp.text.lower()
        if "not built" in text:
            pass  # 未构建时是 JSON 消息，合理
        else:
            # 已构建时返回 index.html，不应包含 editor 标识
            assert "vault editor" not in text


class TestCORS:
    """CORS 响应头 — 扩展侧跨源请求必须通过"""

    def test_cors_preflight_options(self):
        import everlingo.gateway.web_acceptor as wa
        wa._gateway = _make_gateway()
        client = TestClient(app)
        # 先创建 session 以获取有效 session_id
        post_resp = client.post("/api/session")
        sid = post_resp.json()["session_id"]

        # OPTIONS 预检请求
        resp = client.options(
            f"/api/session/{sid}/message",
            headers={
                "Origin": "chrome-extension://test-extension-id",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "*"

    def test_cors_header_on_post_session(self):
        import everlingo.gateway.web_acceptor as wa
        wa._gateway = _make_gateway()
        client = TestClient(app)
        resp = client.post(
            "/api/session",
            headers={"Origin": "chrome-extension://test-extension-id"},
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "*"

    def test_cors_middleware_installed(self):
        from everlingo.gateway.web_acceptor import app as _app
        middleware_types = [m.cls for m in _app.user_middleware]
        from fastapi.middleware.cors import CORSMiddleware
        assert CORSMiddleware in middleware_types


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


class TestGracefulShutdown:
    """WebSessionAcceptor uvicorn 配置中的 shutdown 超时。"""

    @pytest.mark.asyncio
    async def test_timeout_graceful_shutdown_is_2_seconds(self):
        from unittest.mock import patch, MagicMock, AsyncMock

        import everlingo.gateway.web_acceptor as wa

        captured_kwargs = {}
        original_config = wa.uvicorn.Config

        class CaptureConfig(original_config):
            def __init__(self, *args, **kwargs):
                captured_kwargs.update(kwargs)
                super().__init__(*args, **kwargs)

        mock_server = MagicMock()
        mock_server.serve = AsyncMock(return_value=None)

        with patch.object(wa, "uvicorn") as mock_uvicorn:
            mock_uvicorn.Config = CaptureConfig
            mock_uvicorn.Server = MagicMock(return_value=mock_server)

            acc = wa.WebSessionAcceptor()
            gateway = MagicMock()
            task = await acc.start(gateway)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert captured_kwargs.get("timeout_graceful_shutdown") == 2.0
