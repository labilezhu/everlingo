"""
单元测试：_invoke_llm_with_retry

验证：
- 首次成功 → 成功返回
- 瞬态错误 + 重试后成功 → 成功返回
- 全部重试耗尽 → 返回 None
- 永久性错误 → 透传异常
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from openai import (
    APIConnectionError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
)


def _mock_response():
    """Return a mock with status_code for openai exceptions."""
    return MagicMock(status_code=500)

from everlingo.agents.agent import _invoke_llm_with_retry


@pytest.fixture
def mock_agent():
    return AsyncMock()


async def _do(mock_agent, messages=None, max_retries=2):
    return await _invoke_llm_with_retry(mock_agent, messages or [], max_retries=max_retries)


class TestFirstAttemptSucceeds:
    def test_returns_response_directly(self, mock_agent):
        mock_agent.ainvoke.return_value = {"messages": ["ok"]}
        result = asyncio.run(_do(mock_agent))
        assert result == {"messages": ["ok"]}
        assert mock_agent.ainvoke.call_count == 1


class TestRetryOnTransientErrors:
    def test_json_decode_error_then_success(self, mock_agent):
        mock_agent.ainvoke.side_effect = [
            json.JSONDecodeError("Expecting value", "", 0),
            {"messages": ["ok"]},
        ]
        result = asyncio.run(_do(mock_agent))
        assert result == {"messages": ["ok"]}
        assert mock_agent.ainvoke.call_count == 2

    def test_httpx_error_then_success(self, mock_agent):
        mock_agent.ainvoke.side_effect = [
            httpx.TransportError("connection reset"),
            {"messages": ["ok"]},
        ]
        result = asyncio.run(_do(mock_agent))
        assert result == {"messages": ["ok"]}
        assert mock_agent.ainvoke.call_count == 2

    def test_internal_server_error_then_success(self, mock_agent):
        mock_agent.ainvoke.side_effect = [
            InternalServerError("500", response=_mock_response(), body="oops"),
            {"messages": ["ok"]},
        ]
        result = asyncio.run(_do(mock_agent))
        assert result == {"messages": ["ok"]}
        assert mock_agent.ainvoke.call_count == 2

    def test_api_connection_error_then_success(self, mock_agent):
        mock_agent.ainvoke.side_effect = [
            APIConnectionError(request=_mock_response()),
            {"messages": ["ok"]},
        ]
        result = asyncio.run(_do(mock_agent))
        assert result == {"messages": ["ok"]}
        assert mock_agent.ainvoke.call_count == 2


class TestRetryExhausted:
    def test_returns_none_after_all_retries(self, mock_agent):
        error = json.JSONDecodeError("Expecting value", "", 0)
        mock_agent.ainvoke.side_effect = [error, error, error]
        result = asyncio.run(_do(mock_agent))
        assert result is None
        assert mock_agent.ainvoke.call_count == 3  # initial + 2 retries


class TestNonRetryableErrors:
    def test_authentication_error_propagates(self, mock_agent):
        mock_agent.ainvoke.side_effect = AuthenticationError(
            "401", response=_mock_response(), body="bad key"
        )
        with pytest.raises(AuthenticationError):
            asyncio.run(_do(mock_agent))
        assert mock_agent.ainvoke.call_count == 1

    def test_bad_request_error_propagates(self, mock_agent):
        mock_agent.ainvoke.side_effect = BadRequestError(
            "400", response=_mock_response(), body="invalid model"
        )
        with pytest.raises(BadRequestError):
            asyncio.run(_do(mock_agent))
        assert mock_agent.ainvoke.call_count == 1
