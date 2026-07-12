# ref: docs/impl-spec/vault-mcp/vault-mcp-spec.md — MCP Server
# 用 FastMCP in-memory Client 驱动 15 个工具（session.configure + 10 fs + search + vault 管理 2 个 + Utility）。
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


@pytest.fixture
def empty_state(tmp_path: Path, monkeypatch) -> AppState:
    """空 workspace 的 AppState（不预 open en lang；list_vaults 应返空）。
    同时清掉其他测试可能残留的 _current_ws_dir / _current_ws_name。
    """
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    socket_path = tmp_path / "indexer.sock"
    return AppState(socket_path=socket_path, langs=[])


@pytest.fixture
def empty_mcp_client(empty_state: AppState):
    """配合 empty_state 的 MCP client 工厂。"""
    mcp = create_mcp_app(empty_state)

    class _Factory:
        def __call__(self, body: Any) -> _McpClientContext:
            return _McpClientContext(mcp, body)

    return _Factory()


@pytest.fixture
def fresh_workspace(tmp_path: Path, monkeypatch):
    """完全自定义 workspace（不依赖 memory_root / open_state）→ 适用 vault 管理工具测试。"""
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    socket_path = tmp_path / "indexer.sock"
    state = AppState(socket_path=socket_path, langs=[])
    state.open()
    try:
        mcp = create_mcp_app(state)

        class _Factory:
            def __call__(self, body: Any) -> _McpClientContext:
                return _McpClientContext(mcp, body)

        yield _Factory(), state, tmp_path
    finally:
        state.close()


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
        r3 = await c.call_tool(
            "compile_prompt", {"path": "a.md"}, raise_on_error=False
        )
        assert r3.is_error is True
        assert "session not configured" in r3.content[0].text

    with mcp_client(body):
        pass


# ── 2. session.configure 非法 lang ──────────────────────────────────


def test_session_configure_invalid_lang(empty_mcp_client):
    """非法 lang 名（含路径分隔符）被 create_vault 校验拒绝。"""

    async def body(c: Client) -> None:
        r = await c.call_tool(
            "session.configure", {"lang": "a/b"}, raise_on_error=False
        )
        assert r.is_error is True
        assert "auto-create vault failed" in r.content[0].text
        assert "invalid lang" in r.content[0].text


# ── 2b. session.configure 自动创建缺失的 vault ─────────────────────

def test_session_configure_auto_creates_vault(fresh_workspace):
    """lang 在 workspace 不存在 → session.configure 内部调 create_vault，
    vault 目录 + spec/*.md 落盘，session 正常设 lang。"""

    async def body(c: Client) -> None:
        r = await c.call_tool("session.configure", {"lang": "fr"})
        assert r.is_error is False
        assert r.data == {"ok": True, "lang": "fr", "interface_language": None}

        # vault 目录和 spec/*.md 已落盘
        import os
        vault = workspace.lang_vault_dir("fr")
        assert vault.is_dir()
        spec_dir = vault / "spec"
        assert spec_dir.is_dir()
        assert (spec_dir / "vault_spec.md").is_file()
        assert (spec_dir / "events_spec.md").is_file()
        assert (spec_dir / "kb_items_spec_vocab.md").is_file()
        assert (spec_dir / "mem_entry_spec.md").is_file()

        # 后续 fs 工具可用
        r = await c.call_tool("ls", {"path": ""})
        assert r.is_error is False

    factory = fresh_workspace[0]
    with factory(body):
        pass


def test_session_configure_auto_create_failure_propagates(empty_mcp_client):
    """非法 lang 名（"."）经 create_vault 校验 → configure 返回 isError=true。"""

    async def body(c: Client) -> None:
        r = await c.call_tool(
            "session.configure", {"lang": "."}, raise_on_error=False
        )
        assert r.is_error is True
        text = r.content[0].text
        assert "auto-create vault failed" in text
        assert "invalid lang" in text

    with empty_mcp_client(body):
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


# ── 3b. write 工具归一化 frontmatter ──────────────────────────────────


def test_write_normalizes_frontmatter(mcp_client, memory_root: Path):
    """写含坏 frontmatter（裸冒号 / 缺引号等）的内容；落盘后 yaml.safe_load 仍可解析。"""
    import yaml

    rel = "items/vocab/bad-fm--01JZDMC99.md"
    # 故意写坏：headword 值含冒号但未加引号；多出 : 的键
    bad_content = (
        "---\n"
        "ulid: 01JZDMC99\n"
        "headword: take for granted:  期望被当默认值\n"
        "type: vocab\n"
        "---\n\n"
        "# take for granted\n\n正文。\n"
    )

    async def body(c: Client) -> None:
        await c.call_tool("session.configure", {"lang": "en"})
        r = await c.call_tool("write", {"path": rel, "content": bad_content})
        assert r.is_error is False
        assert r.data["ok"] is True

    with mcp_client(body):
        pass

    on_disk = (memory_root / rel).read_text(encoding="utf-8")
    # 落盘 frontmatter 仍可被 yaml.safe_load 解析（归一化后）
    raw, _ = on_disk.split("---\n", 2)[1:3]  # 形如 "---\n<fm>---\n<body>"
    parsed = yaml.safe_load(raw)
    assert isinstance(parsed, dict)
    assert parsed["ulid"] == "01JZDMC99"
    assert parsed["type"] == "vocab"
    # 含冒号的值仍能 round-trip（被引号化或正确转义）
    assert "take for granted" in str(parsed["headword"])
    # 正文原样保留
    assert "# take for granted" in on_disk
    assert "正文。" in on_disk


# ── 3c. 前导斜杠视为 vault 根 ────────────────────────────────────────


def test_leading_slash_treated_as_vault_root(mcp_client, memory_root: Path):
    """ls "/" 等价于 ls ""；read "/a.md" 等价于 read "a.md"。"""

    async def body(c: Client) -> None:
        r = await c.call_tool("session.configure", {"lang": "en"})
        assert r.is_error is False

        # 写一个文件
        r = await c.call_tool("write", {"path": "a.md", "content": "# A\n"})
        assert r.is_error is False

        # ls "" 与 ls "/" 结果一致
        r1 = await c.call_tool("ls", {"path": ""})
        assert r1.is_error is False
        r2 = await c.call_tool("ls", {"path": "/"})
        assert r2.is_error is False
        names1 = {e["name"] for e in r1.data["entries"]}
        names2 = {e["name"] for e in r2.data["entries"]}
        assert names1 == names2
        assert "a.md" in names1

        # read "a.md" 与 read "/a.md" 内容一致
        r3 = await c.call_tool("read", {"path": "a.md"})
        r4 = await c.call_tool("read", {"path": "/a.md"})
        assert r3.is_error is False
        assert r4.is_error is False
        assert r3.data["content"] == r4.data["content"]

        # read "//a.md" 多个前导斜杠也兼容
        r5 = await c.call_tool("read", {"path": "//a.md"})
        assert r5.is_error is False
        assert r5.data["content"] == "# A\n"

        # ls "/items" 访问子目录
        r = await c.call_tool(
            "mkdir", {"path": "/items"}
        )
        assert r.is_error is False
        r = await c.call_tool("write", {"path": "items/b.md", "content": "# B\n"})
        assert r.is_error is False
        r6 = await c.call_tool("ls", {"path": "/items"})
        assert r6.is_error is False
        names6 = [e["name"] for e in r6.data["entries"]]
        assert "b.md" in names6

    with mcp_client(body):
        pass


def test_leading_slash_still_rejects_escape(mcp_client):
    """前导 / strip 后 ../ 仍逃逸 → isError=true。"""

    async def body(c: Client) -> None:
        r = await c.call_tool("session.configure", {"lang": "en"})
        assert r.is_error is False
        r = await c.call_tool(
            "read", {"path": "/../escape.md"}, raise_on_error=False
        )
        assert r.is_error is True
        assert "escape" in r.content[0].text.lower()

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
    """configure en 后 write 走 en vault；再 configure ja 走 ja vault
    （ja vault 不存在，由 session.configure 自动创建）。"""

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
        ja_vault = workspace.lang_vault_dir("ja")
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


# ── 9. initialize.instructions 暴露总览说明 ────────────────────────


def test_initialize_exposes_instructions(open_state: AppState):
    """spec「Server Instructions」：initialize 返回的 instructions 非空且
    覆盖最小契约清单的关键词（session.configure / hybrid / vault / watcher）。"""

    mcp = create_mcp_app(open_state)

    async def body(c: Client) -> None:
        init = await c.initialize()
        # 客户端的 initialize 已被 _McpClientContext 进入时触发；这里再次显式
        # 触发拿结果，便于断言（fastmcp 内部会幂等返回）。
        text = init.instructions or ""
        assert text, "initialize.instructions 应非空"
        # 最小契约关键词
        assert "session.configure" in text
        assert "hybrid" in text
        assert "vault" in text.lower()
        assert "watcher" in text  # 副作用说明关键词
        # vault 管理工具分组 & Utility（15 个工具）
        assert "list_vaults" in text
        assert "create_vault" in text
        assert "gen_id" in text

    with _McpClientContext(mcp, body):
        pass


# ── 10. list_vaults（workspace 级，豁免 configure）───────────────────


def test_list_vaults_empty_workspace(empty_mcp_client):
    """空 workspace → vaults=[] count=0。"""

    async def body(c: Client) -> None:
        r = await c.call_tool("list_vaults", {})
        assert r.is_error is False
        assert r.data == {"vaults": [], "count": 0}

    with empty_mcp_client(body):
        pass


def test_list_vaults_returns_existing(fresh_workspace):
    """含 en / ja 两个 lang vault → 返回该列表（按字典序）。"""
    factory, state, tmp_path = fresh_workspace
    (tmp_path / "memory" / "languages" / "en" / "vault").mkdir(parents=True)
    (tmp_path / "memory" / "languages" / "ja" / "vault").mkdir(parents=True)
    # 一个没有 vault/ 子目录的 lang 目录应被忽略
    (tmp_path / "memory" / "languages" / "no-vault-yet").mkdir(parents=True)

    async def body(c: Client) -> None:
        r = await c.call_tool("list_vaults", {})
        assert r.is_error is False
        assert r.data == {"vaults": ["en", "ja"], "count": 2}

    with factory(body):
        pass


def test_list_vaults_no_configure_required(fresh_workspace):
    """未调 session.configure 也能直接调 list_vaults。"""
    factory, state, tmp_path = fresh_workspace

    async def body(c: Client) -> None:
        r = await c.call_tool("list_vaults", {}, raise_on_error=False)
        assert r.is_error is False
        assert "vaults" in r.data

    with factory(body):
        pass


# ── 11. create_vault（workspace 级，豁免 configure）──────────────────


def test_create_vault_creates_dir_and_spec(fresh_workspace):
    """新 lang：vault 目录 + spec/vault_spec.md 创建，AppState 注册成功。"""
    factory, state, tmp_path = fresh_workspace
    target_lang = "fr"
    expected_vault = tmp_path / "memory" / "languages" / "fr" / "vault"

    async def body(c: Client) -> None:
        r = await c.call_tool("create_vault", {"lang": target_lang})
        assert r.is_error is False
        assert r.data["ok"] is True
        assert r.data["lang"] == target_lang
        assert r.data["vault_path"] == f"memory/languages/{target_lang}/vault"
        assert r.data["created"] is True
        assert r.data["spec_written"] is True
        assert r.data["registered"] is True
        # 文件系统副作用
        assert expected_vault.is_dir()
        spec_dir = expected_vault / "spec"
        assert spec_dir.is_dir()
        for name in ("vault_spec.md", "events_spec.md", "kb_items_spec_vocab.md",
                      "kb_items_spec_phrase.md", "mem_entry_spec.md"):
            assert (spec_dir / name).is_file()
        content = (spec_dir / "vault_spec.md").read_text(encoding="utf-8")
        assert "# 单语言 Memory Vault Spec" in content
        assert "知识点类 memory items" in content

    with factory(body):
        pass

    # AppState._lang_states 已注册（与 open_lang 同一入口）
    assert target_lang in state._lang_states


def test_create_vault_idempotent(fresh_workspace):
    """重复调用 create_vault 不覆盖 spec/*.md、不重建目录。"""
    factory, state, tmp_path = fresh_workspace
    target_lang = "de"
    expected_vault = tmp_path / "memory" / "languages" / "de" / "vault"
    expected_spec_dir = expected_vault / "spec"
    expected_spec_path = expected_spec_dir / "vault_spec.md"

    async def body(c: Client) -> None:
        # 第一次：新建
        r1 = await c.call_tool("create_vault", {"lang": target_lang})
        assert r1.is_error is False
        assert r1.data["created"] is True
        assert r1.data["spec_written"] is True
        original_content = expected_spec_path.read_text(encoding="utf-8")
        # 修改 vault_spec.md（模拟用户/外部编辑）
        expected_spec_path.write_text("USER EDITED\n", encoding="utf-8")
        # 第二次：幂等
        r2 = await c.call_tool("create_vault", {"lang": target_lang})
        assert r2.is_error is False
        assert r2.data["created"] is False
        assert r2.data["spec_written"] is False
        assert r2.data["registered"] is True
        # 第二次未覆盖文件
        assert expected_spec_path.read_text(encoding="utf-8") == "USER EDITED\n"
        # 第一次的内容
        assert original_content.startswith("# 单语言 Memory Vault Spec")
        # 其余 spec 文件 also untouched
        for name in ("events_spec.md", "kb_items_spec_vocab.md"):
            p = expected_spec_dir / name
            assert p.is_file()
            assert p.read_text(encoding="utf-8").startswith("#")

    with factory(body):
        pass


def test_create_vault_rejects_invalid_lang(empty_mcp_client):
    """非法 lang 名（路径分隔符 / 点号 / 空 / NUL）→ isError=true。"""
    invalid = ["", "a/b", "a\\b", ".", "..", "a\0b"]

    async def body(c: Client) -> None:
        for bad in invalid:
            r = await c.call_tool(
                "create_vault", {"lang": bad}, raise_on_error=False
            )
            assert r.is_error is True, f"expected isError for lang={bad!r}"
            assert "invalid lang" in r.content[0].text

    with empty_mcp_client(body):
        pass


def test_create_vault_no_configure_required(fresh_workspace):
    """未调 session.configure 也能直接调 create_vault。"""
    factory, state, tmp_path = fresh_workspace

    async def body(c: Client) -> None:
        r = await c.call_tool("create_vault", {"lang": "it"}, raise_on_error=False)
        assert r.is_error is False
        assert r.data["ok"] is True

    with factory(body):
        pass


def test_create_vault_then_configure_and_search(fresh_workspace):
    """端到端：create_vault 后 session.configure + search 不报错。"""
    factory, state, tmp_path = fresh_workspace
    target_lang = "ko"

    async def body(c: Client) -> None:
        r = await c.call_tool("create_vault", {"lang": target_lang})
        assert r.is_error is False
        # 此时 session.configure(lang=ko) 应成功（vault 目录已建）
        r = await c.call_tool("session.configure", {"lang": target_lang})
        assert r.is_error is False
        assert r.data["lang"] == target_lang
        # 空 vault 调 search 不报错（返回空 hits）
        r = await c.call_tool(
            "search", {"q": "anything", "mode": "exact"}, raise_on_error=False
        )
        assert r.is_error is False
        assert r.data["count"] == 0
        assert r.data["hits"] == []

    with factory(body):
        pass


# ── 13. gen_id（workspace 级 Utility，豁免 configure）────────────────


def test_gen_id_returns_ulid(fresh_workspace):
    """gen_id 返回 26 字符 Crockford base32 ULID。"""
    factory = fresh_workspace[0]

    async def body(c: Client) -> None:
        r = await c.call_tool("gen_id", {})
        assert r.is_error is False
        ulid = r.data["ulid"]
        assert isinstance(ulid, str)
        assert len(ulid) == 26
        # Crockford base32: 0-9 A-H J-K M-N P-T V-Z (excl I, L, O, U)
        import re
        assert re.match(r"^[0-9A-HJKMNP-TV-Z]{26}$", ulid), f"invalid ULID: {ulid}"

    with factory(body):
        pass


def test_gen_id_content_matches_structured_content(fresh_workspace):
    """spec 强制：content[0].text == json.dumps(structured_content)。"""
    factory = fresh_workspace[0]

    async def body(c: Client) -> None:
        r = await c.call_tool("gen_id", {})
        text = r.content[0].text
        sc = r.structured_content
        assert text == json.dumps(sc, ensure_ascii=False, separators=(",", ":"))

    with factory(body):
        pass


def test_gen_id_each_call_unique(fresh_workspace):
    """两次连续调用 gen_id 返回不同的 ULID。"""
    factory = fresh_workspace[0]

    async def body(c: Client) -> None:
        r1 = await c.call_tool("gen_id", {})
        r2 = await c.call_tool("gen_id", {})
        assert r1.data["ulid"] != r2.data["ulid"]

    with factory(body):
        pass


def test_gen_id_does_not_require_configure(fresh_workspace):
    """未调 session.configure 也能直接调 gen_id。"""
    factory = fresh_workspace[0]

    async def body(c: Client) -> None:
        r = await c.call_tool("gen_id", {}, raise_on_error=False)
        assert r.is_error is False
        assert "ulid" in r.data
        assert len(r.data["ulid"]) == 26

    with factory(body):
        pass


# ── 12. grep / find 返回空而非报错当路径不存在 ─────────────────────


def test_grep_returns_empty_when_path_missing(mcp_client):
    """目录 items/vocab 不存在时 grep 返回空 matches，不报 isError。"""

    async def body(c: Client) -> None:
        r = await c.call_tool("session.configure", {"lang": "en"})
        assert r.is_error is False

        r = await c.call_tool(
            "grep", {"query": "ambiguous", "path": "items/vocab"},
            raise_on_error=False,
        )
        assert r.is_error is False, f"grep 不应报错：{r.content[0].text}"
        assert r.data["matches"] == []

    with mcp_client(body):
        pass


def test_find_returns_empty_when_path_missing(mcp_client):
    """目录不存在时 find 返回空 files，不报 isError。"""

    async def body(c: Client) -> None:
        r = await c.call_tool("session.configure", {"lang": "en"})
        assert r.is_error is False

        r = await c.call_tool(
            "find", {"pattern": "*.md", "path": "items/vocab"},
            raise_on_error=False,
        )
        assert r.is_error is False, f"find 不应报错：{r.content[0].text}"
        assert r.data["files"] == []

    with mcp_client(body):
        pass


def test_grep_still_errors_on_path_escape(mcp_client):
    """路径逃逸校验仍应报错（搜索类工具只降级"不存在"，不降级逃逸）。"""

    async def body(c: Client) -> None:
        r = await c.call_tool("session.configure", {"lang": "en"})
        assert r.is_error is False

        r = await c.call_tool(
            "grep", {"query": "x", "path": "../escape.md"},
            raise_on_error=False,
        )
        assert r.is_error is True
        assert "escape" in r.content[0].text.lower()

    with mcp_client(body):
        pass


def test_find_still_errors_on_path_escape(mcp_client):
    """find 的路径逃逸校验仍应报错。"""

    async def body(c: Client) -> None:
        r = await c.call_tool("session.configure", {"lang": "en"})
        assert r.is_error is False

        r = await c.call_tool(
            "find", {"pattern": "*.md", "path": ".."},
            raise_on_error=False,
        )
        assert r.is_error is True
        assert "escape" in r.content[0].text.lower()

    with mcp_client(body):
        pass


# ── 14. compile_prompt ──────────────────────────────────────────────


def test_compile_prompt_expands_include(mcp_client, memory_root: Path):
    """写入主文件（含 {{ include }} 指令）+ 被引用文件 → compile_prompt
    返回已展开的内容，frontmatter 被剥离。"""
    # 被引用文件
    ref_path = memory_root / "refs" / "greeting.md"
    ref_path.parent.mkdir(parents=True)
    ref_path.write_text("---\nulid: REF01\n---\n\nHello World\n", encoding="utf-8")
    # 主文件引用 refs/greeting.md
    main_path = memory_root / "prompts" / "welcome.md"
    main_path.parent.mkdir(parents=True)
    main_path.write_text(
        "# Welcome\n\n{{ include [greeting](../refs/greeting.md) }}\n\nFooter\n",
        encoding="utf-8",
    )

    async def body(c: Client) -> None:
        r = await c.call_tool("session.configure", {"lang": "en"})
        assert r.is_error is False
        r = await c.call_tool(
            "compile_prompt", {"path": "prompts/welcome.md"}
        )
        assert r.is_error is False
        content = r.data["content"]
        # frontmatter 被剥离（主文件无 frontmatter 则不剥离；引用文件的 frontmatter 被剥离）
        assert "REF01" not in content
        # include 被展开 → 包含引用文件内容
        assert "Hello World" in content
        # 主文件自身内容保留
        assert "# Welcome" in content
        assert "Footer" in content
        # include 指令本身被移除
        assert "{{ include" not in content
        assert r.data["path"] == "prompts/welcome.md"

    with mcp_client(body):
        pass


def test_compile_prompt_file_not_found(mcp_client):
    """路径不存在 → isError=true。"""

    async def body(c: Client) -> None:
        r = await c.call_tool("session.configure", {"lang": "en"})
        assert r.is_error is False
        r = await c.call_tool(
            "compile_prompt", {"path": "nonexistent.md"},
            raise_on_error=False,
        )
        assert r.is_error is True
        assert "file not found" in r.content[0].text.lower()

    with mcp_client(body):
        pass


def test_compile_prompt_path_escape(mcp_client):
    """../ 逃逸 → isError=true。"""

    async def body(c: Client) -> None:
        r = await c.call_tool("session.configure", {"lang": "en"})
        assert r.is_error is False
        r = await c.call_tool(
            "compile_prompt", {"path": "../escape.md"},
            raise_on_error=False,
        )
        assert r.is_error is True
        assert "escape" in r.content[0].text.lower()

    with mcp_client(body):
        pass


def test_compile_prompt_content_matches_structured_content(
    mcp_client, memory_root: Path
):
    """content[0].text == json.dumps(structured_content)。"""
    ref_path = memory_root / "refs" / "hello.md"
    ref_path.parent.mkdir(parents=True)
    ref_path.write_text("# Hello\n", encoding="utf-8")
    main_path = memory_root / "prompts" / "main.md"
    main_path.parent.mkdir(parents=True)
    main_path.write_text(
        "{{ include [hello](../refs/hello.md) }}", encoding="utf-8"
    )

    async def body(c: Client) -> None:
        r = await c.call_tool("session.configure", {"lang": "en"})
        assert r.is_error is False
        r = await c.call_tool(
            "compile_prompt", {"path": "prompts/main.md"}
        )
        text = r.content[0].text
        sc = r.structured_content
        assert text == json.dumps(sc, ensure_ascii=False, separators=(",", ":"))

    with mcp_client(body):
        pass
