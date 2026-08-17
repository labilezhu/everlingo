from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from everlingo.gateway.vault_editor_api import router
from everlingo.image.image_store import sha256_of_bytes
from everlingo.workspace import init_workspace_dir, lang_vault_dir


# ── Mock helpers ──────────────────────────────────────────────────


class _MockCtx:
    """Async context manager that yields a given session."""

    def __init__(self, session: Any) -> None:
        self._session = session

    async def __aenter__(self) -> Any:
        return self._session

    async def __aexit__(self, *args: Any) -> None:
        pass


class _MockProfile:
    """Minimal stand-in for UserProfile with a `language.target_language`."""

    def __init__(self, target_language: str = "") -> None:
        self.language = _MockLanguage(target_language)


class _MockLanguage:
    def __init__(self, target_language: str) -> None:
        self.target_language = target_language


def _fake_result(data: dict) -> AsyncMock:
    """Return a mock `call_tool` result with `content[0].text = json.dumps(data)`."""
    r = AsyncMock()
    r.content = [AsyncMock()]
    r.content[0].text = json.dumps(data)
    r.isError = False
    return r


def _error_result(text: str) -> AsyncMock:
    """Return a mock `call_tool` error result."""
    r = AsyncMock()
    r.content = [AsyncMock()]
    r.content[0].text = text
    r.isError = True
    return r


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def client() -> TestClient:
    _app = FastAPI()
    _app.include_router(router)
    return TestClient(_app)


def _patch_ctx(mock_session: AsyncMock) -> tuple[Any, Any]:
    """Patch _configured and _workspace helpers to return mock_session."""

    def _mk_configured(_lang: str) -> _MockCtx:
        return _MockCtx(mock_session)

    def _mk_workspace() -> _MockCtx:
        return _MockCtx(mock_session)

    p1 = patch(
        "everlingo.gateway.vault_editor_api._configured",
        side_effect=_mk_configured,
    )
    p2 = patch(
        "everlingo.gateway.vault_editor_api._workspace",
        side_effect=_mk_workspace,
    )
    p1.start()
    p2.start()
    return p1, p2


# ── Tests ────────────────────────────────────────────────────────


class TestListLangs:
    def test_returns_vaults(self, client: TestClient):
        session = AsyncMock()
        session.call_tool = AsyncMock(return_value=_fake_result({"vaults": ["en", "ja"], "count": 2}))
        p1, p2 = _patch_ctx(session)
        p_profile = patch(
            "everlingo.gateway.vault_editor_api.load_profile",
            return_value=_MockProfile(target_language=""),
        )
        p_profile.start()
        try:
            resp = client.get("/api/vault/langs")
            assert resp.status_code == 200
            data = resp.json()
            assert data["vaults"] == ["en", "ja"]
            assert data["default"] == ""
        finally:
            p1.stop()
            p2.stop()
            p_profile.stop()

    def test_default_injected_from_profile(self, client: TestClient):
        session = AsyncMock()
        session.call_tool = AsyncMock(return_value=_fake_result({"vaults": ["en", "ja"], "count": 2}))
        p1, p2 = _patch_ctx(session)
        p_profile = patch(
            "everlingo.gateway.vault_editor_api.load_profile",
            return_value=_MockProfile(target_language="ja"),
        )
        p_profile.start()
        try:
            resp = client.get("/api/vault/langs")
            assert resp.status_code == 200
            data = resp.json()
            assert data["vaults"] == ["en", "ja"]
            assert data["default"] == "ja"
        finally:
            p1.stop()
            p2.stop()
            p_profile.stop()

    def test_503_when_indexer_offline(self, client: TestClient):
        with patch(
            "everlingo.gateway.vault_editor_api._workspace",
            side_effect=HTTPException(503, detail="indexer offline"),
        ):
            resp = client.get("/api/vault/langs")
            assert resp.status_code == 503
            assert "indexer offline" in resp.json()["detail"]


class TestTree:
    def test_returns_entries(self, client: TestClient, tmp_path: Path):
        session = AsyncMock()
        mcp_data = {
            "path": "",
            "depth": 2,
            "entries": [
                {"name": "items", "path": "items", "type": "dir", "children": []},
                {"name": "events", "path": "events", "type": "dir", "children": []},
            ],
        }
        session.call_tool = AsyncMock(return_value=_fake_result(mcp_data))
        p1, p2 = _patch_ctx(session)
        p3_vault = patch(
            "everlingo.gateway.vault_editor_api.lang_vault_dir",
            return_value=tmp_path / "fake-vault",
        )
        p3_vault.start()
        try:
            resp = client.get("/api/vault/en/tree")
            assert resp.status_code == 200
            # _inject_titles 对无 index.md 的空目录不会注入 title
            assert resp.json() == mcp_data
            session.call_tool.assert_awaited_with("tree", {"path": "", "depth": 2})
        finally:
            p1.stop()
            p2.stop()
            p3_vault.stop()

    def test_filters_tmp_by_default(self, client: TestClient):
        session = AsyncMock()
        session.call_tool = AsyncMock(
            return_value=_fake_result(
                {
                    "path": "",
                    "depth": 2,
                    "entries": [
                        {
                            "name": "items",
                            "path": "items",
                            "type": "dir",
                            "children": [
                                {"name": "vocab", "path": "items/vocab", "type": "dir", "children": []}
                            ],
                        },
                        {"name": "tmp", "path": "tmp", "type": "dir", "children": []},
                    ],
                }
            )
        )
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.get("/api/vault/en/tree")
            assert resp.status_code == 200
            names = [e["name"] for e in resp.json()["entries"]]
            assert "tmp" not in names
            assert "items" in names
        finally:
            p1.stop()
            p2.stop()

    def test_include_tmp_preserves_tmp(self, client: TestClient):
        session = AsyncMock()
        session.call_tool = AsyncMock(
            return_value=_fake_result(
                {
                    "path": "",
                    "depth": 2,
                    "entries": [
                        {"name": "tmp", "path": "tmp", "type": "dir", "children": []}
                    ],
                }
            )
        )
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.get("/api/vault/en/tree?include_tmp=true")
            assert resp.status_code == 200
            names = [e["name"] for e in resp.json()["entries"]]
            assert "tmp" in names
        finally:
            p1.stop()
            p2.stop()

    def test_with_path_returns_subtree(self, client: TestClient):
        session = AsyncMock()
        mcp_data = {
            "path": "items/grammar",
            "depth": 2,
            "entries": [
                {"name": "nouns.md", "path": "items/grammar/nouns.md", "type": "file"},
            ],
        }
        session.call_tool = AsyncMock(return_value=_fake_result(mcp_data))
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.get("/api/vault/en/tree?path=items%2Fgrammar&depth=2")
            assert resp.status_code == 200
            assert resp.json() == mcp_data
            session.call_tool.assert_awaited_with(
                "tree", {"path": "items/grammar", "depth": 2}
            )
        finally:
            p1.stop()
            p2.stop()

    def test_404_on_unknown_lang(self, client: TestClient):
        session = AsyncMock()
        session.call_tool = AsyncMock(
            return_value=_error_result("lang not found in workspace: xx")
        )
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.get("/api/vault/xx/tree")
            assert resp.status_code == 404
        finally:
            p1.stop()
            p2.stop()

    def test_filters_hidden_entries(self, client: TestClient):
        session = AsyncMock()
        session.call_tool = AsyncMock(
            return_value=_fake_result(
                {
                    "path": "",
                    "depth": 2,
                    "entries": [
                        {
                            "name": ".git",
                            "path": ".git",
                            "type": "dir",
                            "children": [
                                {"name": "config", "path": ".git/config", "type": "file"},
                            ],
                        },
                        {
                            "name": ".obsidian",
                            "path": ".obsidian",
                            "type": "dir",
                            "children": [],
                        },
                        {"name": ".DS_Store", "path": ".DS_Store", "type": "file"},
                        {
                            "name": "items",
                            "path": "items",
                            "type": "dir",
                            "children": [
                                {"name": "vocab.md", "path": "items/vocab.md", "type": "file"}
                            ],
                        },
                    ],
                }
            )
        )
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.get("/api/vault/en/tree")
            assert resp.status_code == 200
            names = [e["name"] for e in resp.json()["entries"]]
            assert ".git" not in names
            assert ".obsidian" not in names
            assert ".DS_Store" not in names
            assert "items" in names
            # verify recursion: .git's children are not returned via parent
            items_entry = next(e for e in resp.json()["entries"] if e["name"] == "items")
            assert items_entry["children"][0]["name"] == "vocab.md"
        finally:
            p1.stop()
            p2.stop()

    def test_include_tmp_still_filters_hidden(self, client: TestClient):
        """?include_tmp=true 保留 tmp 但仍过滤隐藏条目（正交）。"""
        session = AsyncMock()
        session.call_tool = AsyncMock(
            return_value=_fake_result(
                {
                    "path": "",
                    "depth": 2,
                    "entries": [
                        {"name": "tmp", "path": "tmp", "type": "dir", "children": []},
                        {"name": ".git", "path": ".git", "type": "dir", "children": []},
                    ],
                }
            )
        )
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.get("/api/vault/en/tree?include_tmp=true")
            assert resp.status_code == 200
            names = [e["name"] for e in resp.json()["entries"]]
            assert "tmp" in names
            assert ".git" not in names
        finally:
            p1.stop()
            p2.stop()

    def test_filters_hidden_in_subtree(self, client: TestClient):
        """path= 子树请求中的隐藏条目也被过滤。"""
        session = AsyncMock()
        session.call_tool = AsyncMock(
            return_value=_fake_result(
                {
                    "path": "items/grammar",
                    "depth": 2,
                    "entries": [
                        {"name": ".cache", "path": "items/grammar/.cache", "type": "dir", "children": []},
                        {"name": "nouns.md", "path": "items/grammar/nouns.md", "type": "file"},
                    ],
                }
            )
        )
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.get("/api/vault/en/tree?path=items%2Fgrammar")
            assert resp.status_code == 200
            names = [e["name"] for e in resp.json()["entries"]]
            assert ".cache" not in names
            assert "nouns.md" in names
        finally:
            p1.stop()
            p2.stop()


class TestRead:
    def test_returns_content(self, client: TestClient):
        session = AsyncMock()
        session.call_tool = AsyncMock(
            return_value=_fake_result({"path": "test.md", "content": "# hello", "size_bytes": 8})
        )
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.get("/api/vault/en/read", params={"path": "test.md"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["path"] == "test.md"
            assert data["content"] == "# hello"
        finally:
            p1.stop()
            p2.stop()

    def test_404_on_missing_file(self, client: TestClient):
        session = AsyncMock()
        session.call_tool = AsyncMock(
            return_value=_error_result("No such file or directory")
        )
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.get("/api/vault/en/read", params={"path": "nope.md"})
            assert resp.status_code == 404
        finally:
            p1.stop()
            p2.stop()


class TestWrite:
    def test_writes_content(self, client: TestClient):
        session = AsyncMock()
        session.call_tool = AsyncMock(
            return_value=_fake_result({"ok": True, "path": "test.md", "bytes_written": 8})
        )
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.post(
                "/api/vault/en/write",
                json={"path": "test.md", "content": "# hello"},
            )
            assert resp.status_code == 200
            assert resp.json()["ok"] is True
            session.call_tool.assert_awaited_with(
                "write", {"path": "test.md", "content": "# hello"}
            )
        finally:
            p1.stop()
            p2.stop()


class TestAppend:
    def test_appends_content(self, client: TestClient):
        session = AsyncMock()
        session.call_tool = AsyncMock(
            return_value=_fake_result({"ok": True, "path": "test.md", "bytes_appended": 6, "new_size_bytes": 14})
        )
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.post(
                "/api/vault/en/append",
                json={"path": "test.md", "content": "\n## more"},
            )
            assert resp.status_code == 200
            assert resp.json()["ok"] is True
            session.call_tool.assert_awaited_with(
                "append", {"path": "test.md", "content": "\n## more"}
            )
        finally:
            p1.stop()
            p2.stop()


class TestMkdir:
    def test_creates_dir(self, client: TestClient):
        session = AsyncMock()
        session.call_tool = AsyncMock(
            return_value=_fake_result({"ok": True, "path": "newdir"})
        )
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.post("/api/vault/en/mkdir", json={"path": "newdir"})
            assert resp.status_code == 200
            assert resp.json()["ok"] is True
            session.call_tool.assert_awaited_with("mkdir", {"path": "newdir"})
        finally:
            p1.stop()
            p2.stop()


class TestDelete:
    def test_deletes_file(self, client: TestClient):
        session = AsyncMock()
        session.call_tool = AsyncMock(
            return_value=_fake_result({"ok": True, "path": "old.md"})
        )
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.post("/api/vault/en/delete", json={"path": "old.md"})
            assert resp.status_code == 200
            assert resp.json()["ok"] is True
            session.call_tool.assert_awaited_with("delete", {"path": "old.md"})
        finally:
            p1.stop()
            p2.stop()


class TestRename:
    def test_renames_file(self, client: TestClient):
        session = AsyncMock()
        # stat → exists=false; read → ok; write → ok; delete → ok
        session.call_tool = AsyncMock(side_effect=[
            _fake_result({"path": "bar.md", "exists": False}),  # stat to
            _fake_result({"path": "foo.md", "content": "# hello", "size_bytes": 8}),  # read from
            _fake_result({"ok": True, "path": "bar.md", "bytes_written": 8}),  # write to
            _fake_result({"ok": True, "path": "foo.md"}),  # delete from
        ])
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.post(
                "/api/vault/en/rename",
                json={"source": "foo.md", "target": "bar.md"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True
            assert data["source"] == "foo.md"
            assert data["target"] == "bar.md"
            # Verify the call sequence
            calls = [c[0] for c in session.call_tool.await_args_list]
            assert calls[0] == ("stat", {"path": "bar.md"})
            assert calls[1] == ("read", {"path": "foo.md"})
            assert calls[2] == ("write", {"path": "bar.md", "content": "# hello"})
            assert calls[3] == ("delete", {"path": "foo.md"})
        finally:
            p1.stop()
            p2.stop()

    def test_409_when_target_exists(self, client: TestClient):
        session = AsyncMock()
        session.call_tool = AsyncMock(
            return_value=_fake_result({"path": "bar.md", "exists": True})
        )
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.post(
                "/api/vault/en/rename",
                json={"source": "foo.md", "target": "bar.md"},
            )
            assert resp.status_code == 409
            # Only stat was called (no read/write/delete)
            session.call_tool.assert_awaited_once_with("stat", {"path": "bar.md"})
        finally:
            p1.stop()
            p2.stop()

    def test_404_when_source_not_found(self, client: TestClient):
        session = AsyncMock()
        session.call_tool = AsyncMock(side_effect=[
            _fake_result({"path": "bar.md", "exists": False}),
            _error_result("No such file"),
        ])
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.post(
                "/api/vault/en/rename",
                json={"source": "nope.md", "target": "bar.md"},
            )
            assert resp.status_code == 404
            # Only stat + read
            assert len(session.call_tool.await_args_list) == 2
        finally:
            p1.stop()
            p2.stop()

    def test_500_when_write_succeeds_but_delete_fails(self, client: TestClient):
        session = AsyncMock()
        session.call_tool = AsyncMock(side_effect=[
            _fake_result({"path": "bar.md", "exists": False}),
            _fake_result({"path": "foo.md", "content": "# hello", "size_bytes": 8}),
            _fake_result({"ok": True, "path": "bar.md", "bytes_written": 8}),
            _error_result("permission denied"),
        ])
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.post(
                "/api/vault/en/rename",
                json={"source": "foo.md", "target": "bar.md"},
            )
            assert resp.status_code == 500
            detail = resp.json()["detail"]
            assert "renamed to bar.md" in detail
            assert "failed to delete source foo.md" in detail
        finally:
            p1.stop()
            p2.stop()


class TestSearch:
    def test_basic_search(self, client: TestClient):
        session = AsyncMock()
        hits = [
            {
                "ulid": "01ABCD",
                "kind": "item",
                "file_path": "items/vocab/test.md",
                "title": "test",
                "score": 0.5,
                "source": "hybrid",
                "snippet": "test snippet",
            }
        ]
        session.call_tool = AsyncMock(
            return_value=_fake_result({"hits": hits, "count": 1, "took_ms": 5.0})
        )
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.post(
                "/api/vault/en/search",
                json={"q": "test", "mode": "hybrid", "limit": 10},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["hits"]) == 1
            session.call_tool.assert_awaited_with(
                "search", {"q": "test", "mode": "hybrid", "limit": 10}
            )
        finally:
            p1.stop()
            p2.stop()

    def test_search_with_tags(self, client: TestClient):
        session = AsyncMock()
        session.call_tool = AsyncMock(
            return_value=_fake_result({"hits": [], "count": 0, "took_ms": 1.0})
        )
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.post(
                "/api/vault/en/search",
                json={"q": "god", "tags": ["vocab"], "tags_op": "and"},
            )
            assert resp.status_code == 200
            session.call_tool.assert_awaited_with(
                "search", {"q": "god", "mode": "hybrid", "limit": 10, "tags": ["vocab"], "tags_op": "and"}
            )
        finally:
            p1.stop()
            p2.stop()

    def test_search_tag_only_q_empty(self, client: TestClient):
        """q 不传或传空字符串，仅 tag 过滤应当正常调用 MCP。"""
        session = AsyncMock()
        session.call_tool = AsyncMock(
            return_value=_fake_result({"hits": [], "count": 0, "took_ms": 1.0})
        )
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.post(
                "/api/vault/en/search",
                json={"tags": ["vocab"], "tags_op": "and"},
            )
            assert resp.status_code == 200
            session.call_tool.assert_awaited_with(
                "search", {"q": "", "mode": "hybrid", "limit": 10, "tags": ["vocab"], "tags_op": "and"}
            )
        finally:
            p1.stop()
            p2.stop()


class TestListTags:
    def test_returns_tags(self, client: TestClient):
        session = AsyncMock()
        session.call_tool = AsyncMock(
            return_value=_fake_result({"tags": [{"tag": "vocab", "count": 5}], "total": 1})
        )
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.get("/api/vault/en/tags")
            assert resp.status_code == 200
            assert resp.json()["tags"][0]["tag"] == "vocab"
        finally:
            p1.stop()
            p2.stop()

    def test_tags_with_filters(self, client: TestClient):
        session = AsyncMock()
        session.call_tool = AsyncMock(
            return_value=_fake_result({"tags": [], "total": 0})
        )
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.get("/api/vault/en/tags?kind=item&item_type=vocab")
            assert resp.status_code == 200
            session.call_tool.assert_awaited_with(
                "list_tags", {"kind": "item", "item_type": "vocab"}
            )
        finally:
            p1.stop()
            p2.stop()


class TestErrorMapping:
    """Verify _map_mcp_error translates MCP error texts to HTTP status codes."""

    def test_path_escape_returns_400(self, client: TestClient):
        session = AsyncMock()
        session.call_tool = AsyncMock(return_value=_error_result("path escape detected"))
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.get("/api/vault/en/read", params={"path": "../etc/passwd"})
            assert resp.status_code == 400
        finally:
            p1.stop()
            p2.stop()

    def test_not_found_returns_404(self, client: TestClient):
        session = AsyncMock()
        session.call_tool = AsyncMock(return_value=_error_result("No such file or directory"))
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.get("/api/vault/en/read", params={"path": "nope.md"})
            assert resp.status_code == 404
        finally:
            p1.stop()
            p2.stop()

    def test_session_not_configured_returns_500(self, client: TestClient):
        session = AsyncMock()
        session.call_tool = AsyncMock(
            return_value=_error_result("session not configured: call session.configure first")
        )
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.get("/api/vault/en/tree")
            assert resp.status_code == 500
            assert "not configured" in resp.json()["detail"]
        finally:
            p1.stop()
            p2.stop()

    def test_unknown_lang_returns_404(self, client: TestClient):
        session = AsyncMock()
        session.call_tool = AsyncMock(return_value=_error_result("lang not found in workspace: xx"))
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.get("/api/vault/xx/tree")
            assert resp.status_code == 404
        finally:
            p1.stop()
            p2.stop()

    def test_unknown_error_returns_500(self, client: TestClient):
        session = AsyncMock()
        session.call_tool = AsyncMock(return_value=_error_result("some unexpected error"))
        p1, p2 = _patch_ctx(session)
        try:
            resp = client.get("/api/vault/en/tree")
            assert resp.status_code == 500
        finally:
            p1.stop()
            p2.stop()


# ── Tree title injection ─────────────────────────────────────────


class TestTreeTitle:
    """_inject_titles 从 frontmatter 提取 title 注入 tree 响应。"""

    _MCP_TREE = {
        "path": "",
        "depth": 2,
        "entries": [],
    }

    def _setup(
        self,
        client: TestClient,
        tmp_path: Path,
        entries: list[dict],
        name: str = "en",
    ) -> tuple[Any, Any, Any]:
        vault_root = tmp_path / name
        vault_root.mkdir(parents=True)

        mcp_data = {**self._MCP_TREE, "entries": entries}
        session = AsyncMock()
        session.call_tool = AsyncMock(return_value=_fake_result(mcp_data))
        p1, p2 = _patch_ctx(session)
        p3 = patch(
            "everlingo.gateway.vault_editor_api.lang_vault_dir",
            return_value=vault_root,
        )
        p3.start()
        return vault_root, (p1, p2, p3)

    def _teardown(self, patches: tuple[Any, Any, Any]) -> None:
        for p in patches:
            p.stop()

    def test_file_with_title(self, client: TestClient, tmp_path: Path):
        vault_root, patches = self._setup(
            client,
            tmp_path,
            [{"name": "god.md", "path": "god.md", "type": "file"}],
        )
        try:
            (vault_root / "god.md").write_text(
                "---\ntitle: God 名词辨析\n---\n\nGod 的用法..."
            )
            resp = client.get("/api/vault/en/tree")
            assert resp.status_code == 200
            entry = resp.json()["entries"][0]
            assert entry["title"] == "God 名词辨析"
        finally:
            self._teardown(patches)

    def test_file_without_frontmatter(self, client: TestClient, tmp_path: Path):
        vault_root, patches = self._setup(
            client,
            tmp_path,
            [{"name": "no-fm.md", "path": "no-fm.md", "type": "file"}],
        )
        try:
            (vault_root / "no-fm.md").write_text("Just content without frontmatter")
            resp = client.get("/api/vault/en/tree")
            assert resp.status_code == 200
            assert "title" not in resp.json()["entries"][0]
        finally:
            self._teardown(patches)

    def test_file_without_title_field(self, client: TestClient, tmp_path: Path):
        vault_root, patches = self._setup(
            client,
            tmp_path,
            [{"name": "a.md", "path": "a.md", "type": "file"}],
        )
        try:
            (vault_root / "a.md").write_text(
                "---\ntags: [test]\n---\n\nbody here"
            )
            resp = client.get("/api/vault/en/tree")
            assert resp.status_code == 200
            assert "title" not in resp.json()["entries"][0]
        finally:
            self._teardown(patches)

    def test_file_with_empty_title(self, client: TestClient, tmp_path: Path):
        vault_root, patches = self._setup(
            client,
            tmp_path,
            [{"name": "b.md", "path": "b.md", "type": "file"}],
        )
        try:
            (vault_root / "b.md").write_text(
                "---\ntitle: \n---\n\na note"
            )
            resp = client.get("/api/vault/en/tree")
            assert resp.status_code == 200
            assert "title" not in resp.json()["entries"][0]
        finally:
            self._teardown(patches)

    def test_non_md_file(self, client: TestClient, tmp_path: Path):
        vault_root, patches = self._setup(
            client,
            tmp_path,
            [{"name": "data.json", "path": "data.json", "type": "file"}],
        )
        try:
            (vault_root / "data.json").write_text('{"title": "should not appear"}')
            resp = client.get("/api/vault/en/tree")
            assert resp.status_code == 200
            assert "title" not in resp.json()["entries"][0]
        finally:
            self._teardown(patches)

    def test_index_md_file(self, client: TestClient, tmp_path: Path):
        vault_root, patches = self._setup(
            client,
            tmp_path,
            [{"name": "index.md", "path": "index.md", "type": "file"}],
        )
        try:
            (vault_root / "index.md").write_text(
                "---\ntitle: Should Not Appear\n---\n\ncontent"
            )
            resp = client.get("/api/vault/en/tree")
            assert resp.status_code == 200
            assert "title" not in resp.json()["entries"][0]
        finally:
            self._teardown(patches)

    def test_dir_with_index_md_title(self, client: TestClient, tmp_path: Path):
        vault_root, patches = self._setup(
            client,
            tmp_path,
            [{"name": "items", "path": "items", "type": "dir", "children": []}],
        )
        try:
            (vault_root / "items").mkdir()
            (vault_root / "items" / "index.md").write_text(
                "---\ntitle: 知识点\n---\n\nindex content"
            )
            resp = client.get("/api/vault/en/tree")
            assert resp.status_code == 200
            entry = resp.json()["entries"][0]
            assert entry["title"] == "知识点"
        finally:
            self._teardown(patches)

    def test_dir_without_index_md(self, client: TestClient, tmp_path: Path):
        vault_root, patches = self._setup(
            client,
            tmp_path,
            [{"name": "empty", "path": "empty", "type": "dir", "children": []}],
        )
        try:
            (vault_root / "empty").mkdir()
            resp = client.get("/api/vault/en/tree")
            assert resp.status_code == 200
            assert "title" not in resp.json()["entries"][0]
        finally:
            self._teardown(patches)

    def test_bad_frontmatter(self, client: TestClient, tmp_path: Path):
        vault_root, patches = self._setup(
            client,
            tmp_path,
            [{"name": "c.md", "path": "c.md", "type": "file"}],
        )
        try:
            # 损坏的 frontmatter：内容不合法但不应导致 500
            (vault_root / "c.md").write_text(
                "---\n:bad key: value\n---\n\nbody"
            )
            resp = client.get("/api/vault/en/tree")
            assert resp.status_code == 200
            assert "title" not in resp.json()["entries"][0]
        finally:
            self._teardown(patches)

    def test_file_does_not_exist_on_disk(self, client: TestClient, tmp_path: Path):
        """MCP 返回了文件但磁盘上不存在 → 静默跳过，不抛错。"""
        vault_root, patches = self._setup(
            client,
            tmp_path,
            [{"name": "ghost.md", "path": "ghost.md", "type": "file"}],
        )
        try:
            # 不创建文件
            resp = client.get("/api/vault/en/tree")
            assert resp.status_code == 200
            assert "title" not in resp.json()["entries"][0]
        finally:
            self._teardown(patches)


# ── Raw file endpoints ────────────────────────────────────────────
# ref: docs/ADR/20260816-markdown-image.md — 决策 3 / 决策 4
# GET/PUT /api/vault/raw/{lang}/{vault_rel_path}：纯本地文件系统，不走 MCP。

IMAGE_CACHE_CONTROL = "public, max-age=31536000, immutable"


def _make_png_bytes(size=(64, 48), color=(30, 30, 200)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_jpeg_bytes(size=(64, 48), color=(200, 30, 30)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class TestRawUpload:
    """PUT /api/vault/raw/{lang}/{vault_rel_path}"""

    @pytest.fixture
    def _ws(self, tmp_path: Path):
        init_workspace_dir(tmp_path)
        yield tmp_path
        init_workspace_dir(None)  # 复位全局 workspace，避免污染其它测试

    def _rel(self, src_sha: str, ext: str = ".png") -> str:
        return f"items/vocab/hello-kitty.assets/{src_sha}{ext}"

    def test_upload_success(self, client: TestClient, _ws: Path):
        data = _make_png_bytes()
        src_sha = sha256_of_bytes(data)
        rel = self._rel(src_sha)
        resp = client.put(
            f"/api/vault/raw/en/{rel}",
            files={"file": ("hello.png", data, "image/png")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["image"]["src_resource_sha256"] == src_sha
        assert body["image"]["mime_type"] == "image/png"
        assert (body["image"]["width"], body["image"]["height"]) == (64, 48)
        assert body["image"]["storage_key"] == f"memory://languages/en/vault/{rel}"
        # 物理落盘
        assert (lang_vault_dir("en") / rel).is_file()

    def test_upload_unsupported_mime(self, client: TestClient, _ws: Path):
        data = _make_png_bytes()
        src_sha = sha256_of_bytes(data)
        resp = client.put(
            f"/api/vault/raw/en/{self._rel(src_sha)}",
            files={"file": ("a.gif", data, "image/gif")},
        )
        assert resp.status_code == 415

    def test_upload_empty_file(self, client: TestClient, _ws: Path):
        resp = client.put(
            f"/api/vault/raw/en/{self._rel('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')}",
            files={"file": ("a.png", b"", "image/png")},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "empty file"

    def test_upload_sha_mismatch(self, client: TestClient, _ws: Path):
        data = _make_png_bytes()
        resp = client.put(
            f"/api/vault/raw/en/{self._rel('wrongsha')}",
            files={"file": ("a.png", data, "image/png")},
        )
        assert resp.status_code == 400
        assert "sha256 mismatch" in resp.json()["detail"]

    def test_upload_path_escape(self, client: TestClient, _ws: Path):
        data = _make_png_bytes()
        src_sha = sha256_of_bytes(data)
        # %2e%2e = ".."（URL 编码避免 httpx 在客户端规范化路径）
        resp = client.put(
            f"/api/vault/raw/en/%2e%2e/outside/{src_sha}.png",
            files={"file": ("a.png", data, "image/png")},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "path escape"

    def test_upload_invalid_lang(self, client: TestClient, _ws: Path):
        data = _make_png_bytes()
        src_sha = sha256_of_bytes(data)
        resp = client.put(
            f"/api/vault/raw/%2e%2e/{self._rel(src_sha)}",
            files={"file": ("a.png", data, "image/png")},
        )
        assert resp.status_code == 400

    def test_upload_invalid_image_data(self, client: TestClient, _ws: Path):
        data = b"\x89PNG\r\n\x1a\n" + b"fake-png-content"
        src_sha = sha256_of_bytes(data)
        resp = client.put(
            f"/api/vault/raw/en/{self._rel(src_sha)}",
            files={"file": ("a.png", data, "image/png")},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "invalid image data"

    def test_upload_idempotent(self, client: TestClient, _ws: Path):
        data = _make_png_bytes()
        src_sha = sha256_of_bytes(data)
        rel = self._rel(src_sha)
        url = f"/api/vault/raw/en/{rel}"
        r1 = client.put(url, files={"file": ("a.png", data, "image/png")})
        r2 = client.put(url, files={"file": ("b.png", data, "image/png")})
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert (
            r1.json()["image"]["saved_resource_sha256"]
            == r2.json()["image"]["saved_resource_sha256"]
        )

    def test_upload_scaled_bytes_under_original_sha(self, client: TestClient, _ws: Path):
        """前端 scale 场景：文件名 stem 是 scale 前的原始 sha，正文是缩放后的字节。"""
        original = _make_png_bytes(size=(2000, 1600))
        src_sha = sha256_of_bytes(original)
        scaled = _make_png_bytes(size=(640, 480), color=(9, 9, 9))
        resp = client.put(
            f"/api/vault/raw/en/{self._rel(src_sha)}",
            files={"file": ("scaled.png", scaled, "image/png")},
        )
        assert resp.status_code == 200
        assert resp.json()["image"]["src_resource_sha256"] == src_sha
        assert (lang_vault_dir("en") / self._rel(src_sha)).is_file()


class TestRawGet:
    """GET /api/vault/raw/{lang}/{vault_rel_path}"""

    @pytest.fixture
    def _ws(self, tmp_path: Path):
        init_workspace_dir(tmp_path)
        yield tmp_path
        init_workspace_dir(None)

    def _write(self, rel: str, data: bytes) -> Path:
        p = lang_vault_dir("en") / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def test_returns_image_bytes_inline(self, client: TestClient, _ws: Path):
        data = _make_png_bytes()
        src_sha = sha256_of_bytes(data)
        rel = self._write(f"items/vocab/hello-kitty.assets/{src_sha}.png", data)
        resp = client.get(f"/api/vault/raw/en/{rel.relative_to(lang_vault_dir('en'))}")
        assert resp.status_code == 200
        assert resp.content == data
        assert resp.headers["content-type"] == "image/png"
        assert resp.headers["cache-control"] == IMAGE_CACHE_CONTROL

    def test_jpeg_content_type(self, client: TestClient, _ws: Path):
        data = _make_jpeg_bytes()
        src_sha = sha256_of_bytes(data)
        rel = f"photos/{src_sha}.jpg"
        self._write(rel, data)
        resp = client.get(f"/api/vault/raw/en/{rel}")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/jpeg"

    def test_md_content_type_text_plain(self, client: TestClient, _ws: Path):
        self._write("notes/foo.md", b"# hello")
        resp = client.get("/api/vault/raw/en/notes/foo.md")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/plain")

    def test_unknown_extension_octet_stream(self, client: TestClient, _ws: Path):
        self._write("data/blob.bin", b"\x00\x01")
        resp = client.get("/api/vault/raw/en/data/blob.bin")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/octet-stream"

    def test_404_missing_file(self, client: TestClient, _ws: Path):
        resp = client.get("/api/vault/raw/en/nope.png")
        assert resp.status_code == 404

    def test_path_escape(self, client: TestClient, _ws: Path):
        resp = client.get("/api/vault/raw/en/%2e%2e/etc/passwd")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "path escape"

    def test_invalid_lang(self, client: TestClient, _ws: Path):
        resp = client.get("/api/vault/raw/%2e%2e/a.png")
        assert resp.status_code == 400
