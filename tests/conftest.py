# ref: docs/impl-spec/vault-mcp/vault-mcp-spec.md
# ref: docs/impl-spec/memory-writer-agent-spec.md
# 共用测试 fixture：
#   - mcp_inmem_client(state, ...): in-memory FastMCP transport
#     （从 tests/test_mem_vault_mcp_server.py 抽出共用）
#   - mcp_vault_with_lang(lang): 同步 helper：
#     在测试内启 in-memory MCP server + 调 mcp_vault_connection 拿
#     (session, tools)，供 mem_writer_agent 异步流程同步测试用。
#   - tmp_mcp_workspace: 重定向 workspace + 创建 en lang vault 目录。

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Callable

import pytest
from fastmcp import Client

from everlingo import workspace
from everlingo.mem.vault.mcp_server import create_mcp_app
from everlingo.mem.vault.search.server import AppState


# ── workspace 引导 ──────────────────────────────────────────────────


@pytest.fixture
def tmp_mcp_workspace(tmp_path: Path, monkeypatch) -> Path:
    """重定向 workspace 到 tmp_path 并预建 en lang vault 目录。"""
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    en_vault = tmp_path / "memory" / "languages" / "en" / "vault"
    en_vault.mkdir(parents=True, exist_ok=True)
    return tmp_path


# ── in-memory MCP Client (与 test_mem_vault_mcp_server.py 同样的
#    一次性 asyncio.run 包裹模式；同一 Client 必须同 event loop) ─


class _McpClientContext:
    """Sync `with` 包裹 in-memory MCP Client 的一次性 asyncio.run。

    body 是 `async def body(c: Client) -> None`，与 Client connection
    同 event loop。
    """

    def __init__(self, mcp_app: Any, body: Callable) -> None:
        self._mcp = mcp_app
        self._body = body
        self._err: BaseException | None = None

    def __enter__(self) -> None:
        mcp = self._mcp
        body = self._body

        async def go() -> None:
            async with Client(mcp) as c:
                await body(c)

        try:
            asyncio.run(go())
        except BaseException as e:
            self._err = e

    def __exit__(self, *args: Any) -> None:
        if self._err is not None:
            raise self._err


@pytest.fixture
def mcp_inmem_client(tmp_mcp_workspace: Path):
    """in-memory MCP client 工厂（基于 tmp_mcp_workspace）。

    用法：
        def test_x(mcp_inmem_client):
            async def body(c: Client) -> None: ...
            with mcp_inmem_client(body):
                pass
    """
    socket_path = tmp_mcp_workspace / "indexer.sock"
    state = AppState(socket_path=socket_path, langs=["en"])
    state.open()
    try:
        mcp = create_mcp_app(state)

        class _Factory:
            def __call__(self, body: Callable) -> _McpClientContext:
                return _McpClientContext(mcp, body)

        yield _Factory()
    finally:
        state.close()


# ── mem_writer_agent 异步流程的同步测试 helper ──────────────────


@pytest.fixture
def mcp_inmem_server(tmp_mcp_workspace: Path):
    """fixture：返回一个 ctx manager，patch mcp_vault_connection
    为基于 in-memory FastMCP 传输的实现。

    用法：
        def test_x(mcp_inmem_server, ...):
            with mcp_inmem_server() as state:
                # mcp_vault_connection 已被 patch；期间 _process_batch 等
                # 会通过 in-memory transport 直接调 MCP server。
                agent._process_batch(entries)
    """
    from contextlib import asynccontextmanager, contextmanager
    from unittest.mock import patch
    from langchain_mcp_adapters.tools import load_mcp_tools

    from everlingo.mem.agents import mem_writer_mcp_client

    @contextmanager
    def _make():
        socket_path = tmp_mcp_workspace / "indexer.sock"
        state = AppState(socket_path=socket_path, langs=["en"])
        state.open()
        try:
            mcp = create_mcp_app(state)
            configured_langs: list[str] = []

            @asynccontextmanager
            async def fake_connection(lang: str):
                configured_langs.append(lang)
                client = Client(mcp)
                async with client as c:
                    await c.call_tool(
                        "session.configure", {"lang": lang}
                    )
                    all_tools = await load_mcp_tools(c.session)
                    tools = [
                        t for t in all_tools
                        if t.name in mem_writer_mcp_client.WANTED_TOOLS
                    ] + [mem_writer_mcp_client.mem_gen_id]
                    yield c.session, tools

            with patch(
                "everlingo.mem.agents.mem_writer_agent.mcp_vault_connection",
                fake_connection,
            ), patch(
                "everlingo.mem.agents.mem_writer_mcp_client.mcp_vault_connection",
                fake_connection,
            ):
                yield state, configured_langs
        finally:
            state.close()

    yield _make



# ── gateway.memory_writer 单例重置 ─────────────────────────────────


@pytest.fixture(autouse=True)
def reset_memory_writer_singleton():
    """每个测试后重置 gateway 的 memory_writer 代理。"""
    yield
    try:
        from everlingo.gateway import gateway as gw_mod
        gw_mod.memory_writer._agent = None  # type: ignore[attr-defined]
    except Exception:
        pass


# ── 文件创建等待 helper（写后 watcher 异步落盘用） ────────────────


def wait_for_file(path: Path, timeout_s: float = 2.0) -> bool:
    """轮询文件出现，最多 timeout_s 秒。"""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.02)
    return path.exists()
