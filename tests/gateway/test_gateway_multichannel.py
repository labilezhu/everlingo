"""
Gateway 启动模式单测：explicit flag 单 channel / 无参 config-driven 多 channel。

ref: TEST_STYLE.md
ref: docs/impl-spec/gateway.md — 启动模式语义
ref: docs/impl-spec/workspace-console/ws-console-arch.md §4.2 acceptor 选择规则
"""
import pytest

import everlingo.gateway.gateway as gateway_mod
from everlingo.gateway.gateway import Gateway


class FakeWechatRuntime:
    instances = []

    def __init__(self, auto_start=False, on_bot_exit=None):
        self.auto_start = auto_start
        self.on_bot_exit = on_bot_exit
        FakeWechatRuntime.instances.append(self)


@pytest.fixture(autouse=True)
def _patch_classes(monkeypatch):
    FakeWechatRuntime.instances = []
    monkeypatch.setattr(gateway_mod, "StdioSessionAcceptor", lambda: "stdio")
    monkeypatch.setattr(
        gateway_mod,
        "WebSessionAcceptor",
        lambda host="0.0.0.0", port=8000: ("web", host, port),
    )
    monkeypatch.setattr(gateway_mod, "WechatRuntime", FakeWechatRuntime)
    monkeypatch.setattr(
        gateway_mod,
        "get_web_listener",
        lambda: type("L", (), {"interface": "localhost", "port": 8000})(),
    )
    yield


def _build(channel_type=None, web_enabled=False, wechat_enabled=False):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(gateway_mod, "channel_enabled", lambda name: {"channel_web": web_enabled, "channel_wechat": wechat_enabled}[name])
        gw = Gateway()
        acceptors = gw._build_acceptors(channel_type)
        return gw, acceptors


class TestExplicitFlag:
    def test_wechat_standalone(self):
        gw, acceptors = _build(channel_type="wechat")
        assert len(acceptors) == 1
        assert isinstance(acceptors[0], FakeWechatRuntime)
        assert acceptors[0].auto_start is True
        assert acceptors[0].on_bot_exit is not None  # bot 崩溃 → 退出进程

    def test_web_with_idle_wechat_runtime(self):
        gw, acceptors = _build(channel_type="web")
        assert len(acceptors) == 2
        assert acceptors[0] == ("web", "localhost", 8000)
        assert isinstance(acceptors[1], FakeWechatRuntime)
        assert acceptors[1].auto_start is False  # idle，console 手动启

    def test_stdio_single(self):
        gw, acceptors = _build(channel_type="stdio")
        assert acceptors == ["stdio"]


class TestConfigDriven:
    def test_web_and_wechat_enabled(self):
        gw, acceptors = _build(None, web_enabled=True, wechat_enabled=True)
        assert len(acceptors) == 2
        assert acceptors[0] == ("web", "localhost", 8000)
        assert acceptors[1].auto_start is True  # wechat 自动启动

    def test_web_enabled_wechat_disabled(self):
        gw, acceptors = _build(None, web_enabled=True, wechat_enabled=False)
        assert len(acceptors) == 2
        assert acceptors[0] == ("web", "localhost", 8000)
        assert acceptors[1].auto_start is False  # idle 供 console 控制

    def test_wechat_only_enabled(self):
        gw, acceptors = _build(None, web_enabled=False, wechat_enabled=True)
        assert len(acceptors) == 1
        assert acceptors[0].auto_start is True
        assert acceptors[0].on_bot_exit is not None  # standalone 语义

    def test_none_enabled_falls_back_to_stdio(self):
        gw, acceptors = _build(None, web_enabled=False, wechat_enabled=False)
        assert acceptors == ["stdio"]
