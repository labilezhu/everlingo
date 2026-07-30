"""MasterClient timeout 参数测试。"""

from __future__ import annotations

import httpx
import pytest

from everlingo.ws_router.master_client import MasterClient


class TestMasterClientTimeout:
    def test_default_timeout(self):
        client = MasterClient("http://localhost:8101", "secret")
        assert client._client.timeout == httpx.Timeout(90.0)

    def test_custom_timeout(self):
        client = MasterClient("http://localhost:8101", "secret", timeout=135)
        assert client._client.timeout == httpx.Timeout(135.0)

    def test_timeout_float_conversion(self):
        client = MasterClient("http://localhost:8101", "secret", timeout=60)
        assert isinstance(client._client.timeout, httpx.Timeout)
        assert client._client.timeout == httpx.Timeout(60.0)
