# ref: docs/impl-spec/search/memory-vault-search-spec.md — gateway 侧接口
# 验证 gateway._SearchClientProxy._ensure 安装的 Writer 写后钩子签名正确，
# 且 index_file / delete_file 调用按 (lang, path) 转发给 SearchClient。
# 之前 bug：_hook 只有 2 个参数，与协议 hook(lang, path, op) 不符，被
# mem_writer_tools._fire_post_write 的 try/except 静默吞掉，writer 写后
# 从未真正投递到 indexer。

from __future__ import annotations

from pathlib import Path

import pytest

from everlingo import workspace
from everlingo.gateway import gateway
from everlingo.mem.agents import mem_writer_tools


class _FakeClient:
    """记录 index_file / delete_file 调用的 SearchClient 替身。"""

    def __init__(self) -> None:
        self.index_calls: list[tuple[str, str]] = []
        self.delete_calls: list[tuple[str, str]] = []

    def index_file(self, lang: str, path: str) -> bool:
        self.index_calls.append((lang, path))
        return True

    def delete_file(self, lang: str, path: str) -> bool:
        self.delete_calls.append((lang, path))
        return True


@pytest.fixture
def fake_client(monkeypatch) -> _FakeClient:
    """用 fake 替换 gateway._ensure() 中构造的真实 SearchClient。"""
    fake = _FakeClient()
    # gateway._ensure() 内部 import：
    #     from ..mem.vault.search.client import SearchClient
    # 用 monkeypatch 在 client 模块层替换 SearchClient，使 _ensure()
    # 拿到 fake。FakeClient 同时暴露 index_file / delete_file 即可。
    from everlingo.mem.vault.search import client as client_mod

    monkeypatch.setattr(client_mod, "SearchClient", lambda socket_path: fake)
    return fake


@pytest.fixture
def memory_root(tmp_path: Path, monkeypatch):
    root = tmp_path / "memory" / "languages" / "en" / "vault"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    mem_writer_tools.set_current_lang("en")
    return root


def test_gateway_hook_forwards_index_file(fake_client: _FakeClient, memory_root: Path):
    """gateway 写后钩子应把 (lang, path, 'index') 转发为 index_file(lang, path)。"""
    # 触发 _ensure()：构造代理 + 调任意方法
    proxy = gateway._SearchClientProxy()
    proxy._ensure()  # 装好钩子 + fake 注入

    p = "items/vocab/god--01JZDGW01.md"
    mem_writer_tools.mem_write_file.invoke({"path": p, "content": "x"})

    assert fake_client.index_calls == [("en", p)]
    assert fake_client.delete_calls == []


def test_gateway_hook_forwards_delete_file(fake_client: _FakeClient, memory_root: Path):
    """gateway 写后钩子应把 (lang, path, 'delete') 转发为 delete_file(lang, path)。"""
    proxy = gateway._SearchClientProxy()
    proxy._ensure()

    p = "items/vocab/god--01JZDGW02.md"
    (memory_root / p).parent.mkdir(parents=True, exist_ok=True)
    (memory_root / p).write_text("x", encoding="utf-8")
    mem_writer_tools.mem_remove_file.invoke({"path": p})

    assert fake_client.delete_calls == [("en", p)]
    assert fake_client.index_calls == []


def test_gateway_proxy_uses_indexer_socket_path(monkeypatch, tmp_path: Path):
    """_ensure() 应用 workspace.indexer_socket_path() 构造 SearchClient。"""
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)

    from everlingo.mem.vault.search import client as client_mod

    captured: dict[str, object] = {}

    def fake_ctor(socket_path):
        captured["socket_path"] = socket_path
        return _FakeClient()

    monkeypatch.setattr(client_mod, "SearchClient", fake_ctor)
    proxy = gateway._SearchClientProxy()
    proxy._ensure()
    assert captured["socket_path"] == workspace.indexer_socket_path()
