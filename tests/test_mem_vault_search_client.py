# ref: docs/impl-spec/search/memory-vault-search-spec.md — gateway 侧接口
# indexer 不可达时：search() -> [] + warn；index_file() -> False + warn；
# delete / status / rebuild -> None + warn。

from __future__ import annotations

from pathlib import Path

import pytest

from everlingo.mem.vault.search.client import SearchClient


def test_search_when_unreachable_returns_empty(tmp_path: Path, caplog):
    """socket 不存在时 search() 降级返回 []."""
    sock = tmp_path / "no-such.sock"
    c = SearchClient(sock)
    with caplog.at_level("WARNING"):
        hits = c.search("hello", lang="en")
    assert hits == []


def test_index_file_when_unreachable_returns_false(tmp_path: Path, caplog):
    sock = tmp_path / "no-such.sock"
    c = SearchClient(sock)
    with caplog.at_level("WARNING"):
        ok = c.index_file("en", "items/vocab/foo.md")
    assert ok is False


def test_delete_file_when_unreachable_returns_false(tmp_path: Path):
    sock = tmp_path / "no-such.sock"
    c = SearchClient(sock)
    assert c.delete_file("en", "items/vocab/foo.md") is False


def test_status_when_unreachable_returns_none(tmp_path: Path):
    sock = tmp_path / "no-such.sock"
    c = SearchClient(sock)
    assert c.status() is None


def test_rebuild_when_unreachable_returns_none(tmp_path: Path):
    sock = tmp_path / "no-such.sock"
    c = SearchClient(sock)
    assert c.rebuild("en") is None
