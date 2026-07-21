from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from everlingo.gateway.vault_editor_api import router


# ── Mock helpers ──────────────────────────────────────────────────


class _MockCtx:
    """Async context manager that yields a given session."""

    def __init__(self, session: Any) -> None:
        self._session = session

    async def __aenter__(self) -> Any:
        return self._session

    async def __aexit__(self, *args: Any) -> None:
        pass


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
        try:
            resp = client.get("/api/vault/langs")
            assert resp.status_code == 200
            data = resp.json()
            assert data["vaults"] == ["en", "ja"]
        finally:
            p1.stop()
            p2.stop()

    def test_503_when_indexer_offline(self, client: TestClient):
        with patch(
            "everlingo.gateway.vault_editor_api._workspace",
            side_effect=HTTPException(503, detail="indexer offline"),
        ):
            resp = client.get("/api/vault/langs")
            assert resp.status_code == 503
            assert "indexer offline" in resp.json()["detail"]


class TestTree:
    def test_returns_entries(self, client: TestClient):
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
        try:
            resp = client.get("/api/vault/en/tree")
            assert resp.status_code == 200
            assert resp.json() == mcp_data
            # Verify configure was called with correct lang
            session.call_tool.assert_awaited_with("tree", {"path": "", "depth": 2})
        finally:
            p1.stop()
            p2.stop()

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
