# ref: docs/impl-spec/vault-mcp/valut-mcp-spec.md — MCP Server
# 用 FastMCP in-memory Client 驱动 12 个工具（session.configure + 9 fs + search）。
# 覆盖：未 configure 报错 / invalid lang / configure+fs / 路径逃逸 / hybrid search /
# lang 参数覆盖会话 / 重调切换 / text==structuredContent。
#
# 测试用 sync 写：通过 _McpClientContext 包装 FastMCP async client + _run()
# 包裹异步操作；避免 pytest-asyncio 配置耦合。

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client

from everlingo import workspace
from everlingo.mem.vault.mcp_server import create_mcp_app
from everlingo.mem.vault.search.server import AppState


@pytest.fixture
def memory_root(tmp_path: Path, monkeypatch) -> Path:
    """设置 workspace 到 tmp_path，返回 en lang vault 根。"""
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    root = tmp_path / "memory" / "languages" / "en" / "vault"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def state(tmp_path: Path, memory_root: Path) -> AppState:
    socket_path = tmp_path / "indexer.sock"
    return AppState(socket_path=socket_path, langs=["en"])


@pytest.fixture
def open_state(state: AppState):
    """手动 open/close AppState（不用 TestClient 走 lifespan，因为 MCP 测试不依赖 FastAPI）。"""
    state.open()
    try:
        yield state
    finally:
        state.close()


class _McpClientContext:
    """FastMCP in-memory Client 的 sync 包装（`with mcp_client as c: ...`）。

    ⚠️ 关键约束：Client 的 connection 绑定到它被 enter 的 event loop；
    同一 Client 的所有 call_tool 都必须在该 loop 内运行。
    本 context manager 通过一次性把"进入 Client + 测试 body"放在同一
    asyncio.run() 内解决此问题：测试 body 收一个 sync 回调（拿到 Client），
    在 callback 内跑测试的 async 工作。
    """

    def __init__(self, mcp_app: Any, body: Any) -> None:
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
def mcp_client(open_state: AppState):
    """测试用 MCP client 工厂。形如 `with mcp_client(cb) as _: ...`，
    cb 是 `async def cb(client: Client): ...`，与 Client connection 同 event loop。
    """
    mcp = create_mcp_app(open_state)

    class _Factory:
        def __call__(self, body: Any) -> _McpClientContext:
            return _McpClientContext(mcp, body)

    return _Factory()


def _write_kb_item(memory_root: Path, name: str, ulid: str, body: str) -> Path:
    p = memory_root / "items" / "vocab" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"---\nulid: {ulid}\nslug: {name.split('--')[0]}\ntype: vocab\ntitle: {name.split('--')[0]}\n---\n\n{body}",
        encoding="utf-8",
    )
    return p


async def _wait_for_hit(
    client: Client, tool_args: dict[str, Any], target_ulid: str | None = None,
    timeout_s: float = 5.0
) -> Any:
    """轮询 search 直到 count>=1（或 ulid 命中）。"""
    deadline = time.monotonic() + timeout_s
    last = None
    while time.monotonic() < deadline:
        last = await client.call_tool("search", tool_args)
        if last.data["count"] >= 1 and (
            target_ulid is None
            or any(h["ulid"] == target_ulid for h in last.data["hits"])
        ):
            return last
        await asyncio.sleep(0.2)
    return last


# ── 1. 未 configure 报错 ─────────────────────────────────────────────


def test_session_not_configured_returns_error(mcp_client):
    """未调用 session.configure 直接调 read/search → isError=true + 固定文案。"""

    async def body(c: Client) -> None:
        r = await c.call_tool("read", {"path": "a.md"}, raise_on_error=False)
        assert r.is_error is True
        assert "session not configured" in r.content[0].text
        r2 = await c.call_tool("search", {"q": "anything"}, raise_on_error=False)
        assert r2.is_error is True
        assert "session not configured" in r2.content[0].text

    with mcp_client(body):
        pass


# ── 2. session.configure 非法 lang ──────────────────────────────────


def test_session_configure_invalid_lang(mcp_client):
    """lang 不在 workspace → isError=true。"""

    async def body(c: Client) -> None:
        r = await c.call_tool(
            "session.configure", {"lang": "xx"}, raise_on_error=False
        )
        assert r.is_error is True
        assert "lang not found" in r.content[0].text

    with mcp_client(body):
        pass


# ── 3. configure 后 fs 工具正常 ─────────────────────────────────────


def test_session_configure_then_ls_read_write(mcp_client, memory_root: Path):
    """configure 后写文件、读文件、列目录。"""

    async def body(c: Client) -> None:
        r = await c.call_tool("session.configure", {"lang": "en"})
        assert r.is_error is False
        assert r.data == {"ok": True, "lang": "en", "interface_language": None}

        r = await c.call_tool(
            "write",
            {"path": "items/vocab/hello--01JZDMC01.md", "content": "# hello\n"},
        )
        assert r.is_error is False
        assert r.data["ok"] is True
        assert r.data["bytes_written"] == 8

        r = await c.call_tool(
            "read", {"path": "items/vocab/hello--01JZDMC01.md"}
        )
        assert r.is_error is False
        assert r.data["content"] == "# hello\n"
        assert r.data["size_bytes"] == 8

        r = await c.call_tool("ls", {"path": "items/vocab"})
        assert r.is_error is False
        names = [e["name"] for e in r.data["entries"]]
        assert "hello--01JZDMC01.md" in names

    with mcp_client(body):
        pass


# ── 4. 路径逃逸拒绝 ────────────────────────────────────────────────


def test_path_escape_rejected(mcp_client):
    """../ 试图逃出 vault 根 → isError=true。"""

    async def body(c: Client) -> None:
        r = await c.call_tool("session.configure", {"lang": "en"})
        assert r.is_error is False
        r = await c.call_tool(
            "read", {"path": "../escape.md"}, raise_on_error=False
        )
        assert r.is_error is True
        assert "escapes" in r.content[0].text or "escape" in r.content[0].text

    with mcp_client(body):
        pass


# ── 5. hybrid search 命中 ───────────────────────────────────────────


def test_search_hybrid_returns_hits(mcp_client, memory_root: Path):
    """写一个 kb item → search 命中 → 字段齐全。"""
    _write_kb_item(memory_root, "god--01JZDMC02.md", "01JZDMC02", "deity supreme being")

    async def body(c: Client) -> None:
        r = await c.call_tool("session.configure", {"lang": "en"})
        assert r.is_error is False
        r = await _wait_for_hit(
            c,
            {"q": "deity", "kind": "item", "mode": "hybrid", "limit": 4},
            target_ulid="01JZDMC02",
        )
        assert r is not None and r.data["count"] >= 1, (
            "watcher 未在 5s 内把 kb item 入索引"
        )
        hits = r.data["hits"]
        assert any(h["ulid"] == "01JZDMC02" for h in hits)
        for h in hits:
            assert h["lang"] == "en"
            assert h["source"] in ("fts", "vec", "hybrid")
            assert "snippet" in h

    with mcp_client(body):
        pass


# ── 6. lang 参数覆盖会话 lang ──────────────────────────────────────


def test_search_lang_param_overrides_session(mcp_client, tmp_path: Path, monkeypatch):
    """session=en，传 lang=ja 跨 lang 检索。"""
    ja_vault = tmp_path / "memory" / "languages" / "ja" / "vault"
    ja_vault.mkdir(parents=True)
    _write_kb_item(ja_vault, "ai--01JZDMC03.md", "01JZDMC03", "あいまい ambiguous")

    async def body(c: Client) -> None:
        r = await c.call_tool("session.configure", {"lang": "en"})
        assert r.is_error is False
        r = await _wait_for_hit(
            c,
            {
                "q": "あいまい",
                "lang": "ja",
                "kind": "item",
                "mode": "hybrid",
                "limit": 4,
            },
            target_ulid="01JZDMC03",
        )
        assert r is not None and r.data["count"] >= 1, (
            "watcher 未在 5s 内把 ja kb item 入索引"
        )
        assert r.data["hits"][0]["lang"] == "ja"

    with mcp_client(body):
        pass


# ── 7. 重调切换 lang ────────────────────────────────────────────────


def test_session_reconfigure_switches_lang(mcp_client, memory_root: Path):
    """configure en 后 write 走 en vault；再 configure ja 走 ja vault。"""
    ja_vault = memory_root.parent.parent / "ja" / "vault"
    ja_vault.mkdir(parents=True, exist_ok=True)

    async def body(c: Client) -> None:
        r = await c.call_tool("session.configure", {"lang": "en"})
        assert r.is_error is False
        r = await c.call_tool(
            "write", {"path": "en-file--01JZDMC04.md", "content": "en"}
        )
        assert r.is_error is False

        r = await c.call_tool("session.configure", {"lang": "ja"})
        assert r.is_error is False
        assert r.data["lang"] == "ja"
        r = await c.call_tool(
            "write", {"path": "ja-file--01JZDMC05.md", "content": "ja"}
        )
        assert r.is_error is False
        assert (ja_vault / "ja-file--01JZDMC05.md").exists()
        assert not (memory_root / "ja-file--01JZDMC05.md").exists()

    with mcp_client(body):
        pass


# ── 8. content[0].text == json.dumps(structured_content) ─────────────


def test_structured_content_equals_text(mcp_client, memory_root: Path):
    """spec 强制：content[0].text == json.dumps(structured_content)。"""

    async def body(c: Client) -> None:
        r = await c.call_tool("session.configure", {"lang": "en"})
        assert r.is_error is False
        r = await c.call_tool(
            "write", {"path": "x--01JZDMC06.md", "content": "abc"}
        )
        assert r.is_error is False
        text = r.content[0].text
        sc = r.structured_content
        # FastMCP 用 json.dumps(..., separators=(",", ":")) 序列化 structured_content。
        assert text == json.dumps(sc, ensure_ascii=False, separators=(",", ":")), (
            f"text != json(structured_content): text={text!r} sc={sc!r}"
        )

    with mcp_client(body):
        pass
