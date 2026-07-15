"""
单元测试：LLM 畸形响应体日志钩子

验证：
- 正常 JSON → 无 warning 日志
- 非 JSON 响应 (HTML 错误页) → warning 日志含状态码 + body 片段
- 非 JSON 响应 (截断 JSON) → warning 日志
- UnicodeDecodeError 时 → warning 日志
"""
import asyncio
import logging

import httpx
import pytest

from everlingo.llm import _log_malformed_async_response, _log_malformed_sync_response


class HandlerMock(logging.Handler):
    """Minimal handler to capture log records."""

    def __init__(self, records: list):
        super().__init__()
        self._records = records

    def emit(self, record):
        self._records.append(record)


@pytest.fixture
def records():
    lst = []
    logger = logging.getLogger("everlingo.llm")
    handler = HandlerMock(lst)
    logger.addHandler(handler)
    yield lst
    logger.removeHandler(handler)


class TestAsyncHook:
    def test_valid_json_no_warning(self, records):
        resp = httpx.Response(200, content=b'{"ok": true}')
        asyncio.run(_log_malformed_async_response(resp))
        assert len(records) == 0

    def test_html_error_page_logs_warning(self, records):
        html_body = b"<html><body>502 Bad Gateway</body></html>"
        resp = httpx.Response(502, content=html_body)
        asyncio.run(_log_malformed_async_response(resp))
        assert len(records) == 1
        assert records[0].levelno == logging.WARNING
        msg = records[0].getMessage()
        assert "502" in msg
        assert "502 Bad Gateway" in msg

    def test_truncated_json_logs_warning(self, records):
        truncated = b'{"key": "value"'
        resp = httpx.Response(200, content=truncated)
        asyncio.run(_log_malformed_async_response(resp))
        assert len(records) == 1
        msg = records[0].getMessage()
        assert "200" in msg
        assert truncated.decode() in msg

    def test_empty_body_logs_warning(self, records):
        resp = httpx.Response(500, content=b"")
        asyncio.run(_log_malformed_async_response(resp))
        assert len(records) == 1
        assert records[0].levelno == logging.WARNING

    def test_non_ascii_body_caught_safely(self, records):
        resp = httpx.Response(200, content=b"\xff\xfe\x00\x01")
        asyncio.run(_log_malformed_async_response(resp))
        assert len(records) == 1


class TestSyncHook:
    def test_valid_json_no_warning(self, records):
        resp = httpx.Response(200, content=b'{"ok": true}')
        _log_malformed_sync_response(resp)
        assert len(records) == 0

    def test_html_error_page_logs_warning(self, records):
        html_body = b"<html><body>503 Service Unavailable</body></html>"
        resp = httpx.Response(503, content=html_body)
        _log_malformed_sync_response(resp)
        assert len(records) == 1
        assert records[0].levelno == logging.WARNING
        msg = records[0].getMessage()
        assert "503" in msg
        assert "503 Service Unavailable" in msg

    def test_truncated_json_logs_warning(self, records):
        truncated = b'{"items": [1, 2, 3'
        resp = httpx.Response(200, content=truncated)
        _log_malformed_sync_response(resp)
        assert len(records) == 1
        assert records[0].levelno == logging.WARNING
        assert truncated.decode() in records[0].getMessage()
