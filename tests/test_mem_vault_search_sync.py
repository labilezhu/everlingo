# ref: docs/impl-spec/search/memory-vault-search-spec.md — 启动对账
# reconcile: file_mtime + content_hash diff（upsert/skip）→ 清孤儿 → tokenizer
# 版本比对触发 FTS 重建。

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from everlingo.mem.vault.search import indexer, sync
from everlingo.mem.vault.search.indexer import (
    count_docs,
    index_file,
    init_db,
    set_meta,
)
from everlingo.mem.vault.search.sync import open_db, reconcile


@pytest.fixture
def memory_root(tmp_path: Path) -> Path:
    root = tmp_path / "memory"
    root.mkdir()
    return root


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "index" / "memory.sqlite"


def _write_item(memory_root: Path, name: str, ulid: str, body: str = "x") -> Path:
    p = memory_root / "en" / "items" / "vocab" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\nulid: {ulid}\nslug: {name.split('--')[0]}\ntype: vocab\n---\n\n{body}", encoding="utf-8")
    return p


def test_reconcile_indexes_new_files(db_path: Path, memory_root: Path):
    _write_item(memory_root, "a--01JZB0001.md", "01JZB0001")
    _write_item(memory_root, "b--01JZB0002.md", "01JZB0002")
    conn = open_db(db_path)
    result = reconcile(conn, memory_root)
    assert result.indexed == 2
    assert result.orphans == 0
    assert count_docs(conn) == 2


def test_reconcile_skips_unchanged(db_path: Path, memory_root: Path):
    _write_item(memory_root, "a--01JZB0003.md", "01JZB0003")
    conn = open_db(db_path)
    r1 = reconcile(conn, memory_root)
    assert r1.indexed == 1
    r2 = reconcile(conn, memory_root)
    assert r2.skipped == 1
    assert r2.indexed == 0


def test_reconcile_detects_change(db_path: Path, memory_root: Path):
    p = _write_item(memory_root, "a--01JZB0004.md", "01JZB0004", body="old")
    conn = open_db(db_path)
    reconcile(conn, memory_root)
    p.write_text(
        "---\nulid: 01JZB0004\nslug: a\ntype: vocab\n---\n\nnew body",
        encoding="utf-8",
    )
    r = reconcile(conn, memory_root)
    assert r.indexed == 1


def test_reconcile_cleans_orphans(db_path: Path, memory_root: Path):
    p = _write_item(memory_root, "a--01JZB0005.md", "01JZB0005")
    conn = open_db(db_path)
    reconcile(conn, memory_root)
    assert count_docs(conn) == 1
    p.unlink()
    r = reconcile(conn, memory_root)
    assert r.orphans == 1
    assert count_docs(conn) == 0


def test_reconcile_tokenizer_version_change_triggers_rebuild(db_path: Path, memory_root: Path):
    _write_item(memory_root, "a--01JZB0006.md", "01JZB0006", body="hello world")
    conn = open_db(db_path)
    reconcile(conn, memory_root)
    # 模拟 tokenizer 版本变化
    set_meta(conn, "tokenizer_version", "fake-old-version")
    r = reconcile(conn, memory_root)
    assert r.fts_rebuilt is True
