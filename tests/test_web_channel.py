"""
核心流程测试：WebChannel

ref: TEST_STYLE.md — 只测核心流程和用户输入边缘情况
ref: web-session-acceptor.md — Web Channel 实现
"""
import asyncio

import pytest

from everlingo.gateway.channels.web_channel import WebChannel, SSEEvent


class TestWebChannelRecv:
    """ref: web-session-acceptor.md — recv 行为"""

    @pytest.mark.asyncio
    async def test_recv_returns_message_from_queue(self):
        """recv() 从队列中读取并返回消息文字。"""
        channel = WebChannel()
        await channel._incoming.put("hello")
        result = await channel.recv()
        assert result == "hello"

    @pytest.mark.asyncio
    async def test_recv_returns_none_on_channel_end(self):
        """recv() 收到 None 时返回 None。"""
        channel = WebChannel()
        await channel._incoming.put(None)
        result = await channel.recv()
        assert result is None

    @pytest.mark.asyncio
    async def test_recv_blocks_until_message_available(self):
        """recv() 阻塞直到有消息可用。"""
        channel = WebChannel()

        async def delayed_put():
            await asyncio.sleep(0.01)
            await channel._incoming.put("delayed")

        task = asyncio.create_task(delayed_put())
        result = await channel.recv()
        await task
        assert result == "delayed"

    @pytest.mark.asyncio
    async def test_multiple_messages_in_order(self):
        """多条消息按顺序 recv。"""
        channel = WebChannel()
        await channel._incoming.put("first")
        await channel._incoming.put("second")
        await channel._incoming.put(None)

        assert (await channel.recv()) == "first"
        assert (await channel.recv()) == "second"
        assert (await channel.recv()) is None


class TestWebChannelSSE:
    """ref: web-session-acceptor.md — SSE 推送"""

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all_sse_clients(self):
        """broadcast 发送事件到所有 SSE 客户端。"""
        channel = WebChannel()
        q1 = channel.add_sse_client()
        q2 = channel.add_sse_client()

        await channel.send("test message")
        await channel.send_typing_hint()
        await channel.stop_typing_hint()

        e1 = await q1.get()
        assert e1.event_type == "message"
        assert e1.data["text"] == "test message"

        e2 = await q1.get()
        assert e2.event_type == "typing_hint"
        assert e2.data["typing"] is True

        e3 = await q1.get()
        assert e3.event_type == "typing_hint"
        assert e3.data["typing"] is False

        assert (await q2.get()).event_type == "message"
        assert (await q2.get()).event_type == "typing_hint"
        assert (await q2.get()).event_type == "typing_hint"

    @pytest.mark.asyncio
    async def test_remove_sse_client(self):
        """移除 SSE 客户端后不再收到事件。"""
        channel = WebChannel()
        q1 = channel.add_sse_client()
        q2 = channel.add_sse_client()
        channel.remove_sse_client(q1)

        await channel.send("only for q2")

        assert (await q2.get()).event_type == "message"
        assert q1.qsize() == 0

    @pytest.mark.asyncio
    async def test_send_adds_timestamp_to_event(self):
        """send 产生的事件包含 timestamp。"""
        channel = WebChannel()
        q = channel.add_sse_client()
        await channel.send("hi")
        event = await q.get()
        assert "timestamp" in event.data
        assert isinstance(event.data["timestamp"], str)

    @pytest.mark.asyncio
    async def test_sse_event_format(self):
        """SSEEvent 格式化为正确的 SSE 协议文本。"""
        event = SSEEvent("message", text="你好", message_id="abc")
        formatted = event.format_sse()
        assert formatted.startswith("event: message\ndata: ")
        assert formatted.endswith("\n\n")
        assert '"text": "你好"' in formatted
        assert '"message_id": "abc"' in formatted
        assert '"timestamp"' in formatted


class TestSSEEvent:
    """SSEEvent 单元测试（同步）。"""

    def test_sse_format_typing_hint(self):
        event = SSEEvent("typing_hint", typing=True)
        text = event.format_sse()
        assert "event: typing_hint" in text
        assert '"typing": true' in text

    def test_sse_format_message(self):
        event = SSEEvent("message", text="hello world")
        text = event.format_sse()
        assert "event: message" in text
        assert '"text": "hello world"' in text
