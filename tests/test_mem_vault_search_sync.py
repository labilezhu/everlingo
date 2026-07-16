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


def _write_item(memory_root: Path, name: str, ulid: str, body: str = "x", slug: str | None = None) -> Path:
    """写 kb item 文件。新布局：不含 {lang}/ 前缀。文件名即 {slug}.md。"""
    p = memory_root / "items" / "vocab" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    if slug is None:
        slug = Path(name).stem
    p.write_text(f"---\nulid: {ulid}\nslug: {slug}\ntype: vocab\n---\n\n{body}", encoding="utf-8")
    return p


def test_reconcile_indexes_new_files(db_path: Path, memory_root: Path):
    _write_item(memory_root, "a1.md", "01JZB0001")
    _write_item(memory_root, "b.md", "01JZB0002")
    conn = open_db(db_path)
    result = reconcile(conn, memory_root, "en")
    assert result.indexed == 2
    assert result.orphans == 0
    assert count_docs(conn) == 2


def test_reconcile_skips_unchanged(db_path: Path, memory_root: Path):
    _write_item(memory_root, "a3.md", "01JZB0003")
    conn = open_db(db_path)
    r1 = reconcile(conn, memory_root, "en")
    assert r1.indexed == 1
    r2 = reconcile(conn, memory_root, "en")
    assert r2.skipped == 1
    assert r2.indexed == 0


def test_reconcile_detects_change(db_path: Path, memory_root: Path):
    p = _write_item(memory_root, "a4.md", "01JZB0004", body="old")
    conn = open_db(db_path)
    reconcile(conn, memory_root, "en")
    p.write_text(
        "---\nulid: 01JZB0004\nslug: a\ntype: vocab\n---\n\nnew body",
        encoding="utf-8",
    )
    r = reconcile(conn, memory_root, "en")
    assert r.indexed == 1


def test_reconcile_cleans_orphans(db_path: Path, memory_root: Path):
    p = _write_item(memory_root, "a5.md", "01JZB0005")
    conn = open_db(db_path)
    reconcile(conn, memory_root, "en")
    assert count_docs(conn) == 1
    p.unlink()
    r = reconcile(conn, memory_root, "en")
    assert r.orphans == 1
    assert count_docs(conn) == 0


def test_reconcile_tokenizer_version_change_triggers_rebuild(db_path: Path, memory_root: Path):
    _write_item(memory_root, "a6.md", "01JZB0006", body="hello world")
    conn = open_db(db_path)
    reconcile(conn, memory_root, "en")
    # 模拟 tokenizer 版本变化
    set_meta(conn, "tokenizer_version", "fake-old-version")
    r = reconcile(conn, memory_root, "en")
    assert r.fts_rebuilt is True


def test_reconcile_skips_tmp_directory(db_path: Path, memory_root: Path):
    """tmp/ 子目录下的文件不应被索引。"""
    _write_item(memory_root, "a7.md", "01JZB0007")
    tmp_p = memory_root / "tmp" / "draft.md"
    tmp_p.parent.mkdir(parents=True, exist_ok=True)
    tmp_p.write_text("---\nulid: 01JZB0008\nslug: draft\ntype: vocab\n---\n\nbody", encoding="utf-8")
    conn = open_db(db_path)
    result = reconcile(conn, memory_root, "en")
    assert result.indexed == 1
    assert count_docs(conn) == 1
    assert conn.execute("SELECT ulid FROM documents").fetchone()[0] == "01JZB0007"


def test_reconcile_skips_vault_spec_md(db_path: Path, memory_root: Path):
    """VAULT_SPEC.md（vault 元文件）不应被索引。"""
    _write_item(memory_root, "a9.md", "01JZB0009")
    spec_p = memory_root / "VAULT_SPEC.md"
    spec_p.write_text("# 单语言 Memory Vault Spec\n\n正文\n", encoding="utf-8")
    conn = open_db(db_path)
    result = reconcile(conn, memory_root, "en")
    assert result.indexed == 1
    assert count_docs(conn) == 1
    assert conn.execute("SELECT ulid FROM documents").fetchone()[0] == "01JZB0009"
    rows = conn.execute("SELECT file_path FROM documents").fetchall()
    assert all(not r[0].endswith("VAULT_SPEC.md") for r in rows)


def test_reconcile_skips_spec_subdirectory(db_path: Path, memory_root: Path):
    """spec/ 子目录下 .md 不应被索引。"""
    _write_item(memory_root, "a10.md", "01JZB0010")
    spec_dir = memory_root / "spec"
    spec_dir.mkdir()
    (spec_dir / "vault_spec.md").write_text("# spec\n", encoding="utf-8")
    (spec_dir / "events_spec.md").write_text("# events\n", encoding="utf-8")
    conn = open_db(db_path)
    result = reconcile(conn, memory_root, "en")
    assert result.indexed == 1
    assert count_docs(conn) == 1
    rows = conn.execute("SELECT file_path FROM documents").fetchall()
    assert all("spec/" not in r[0] for r in rows)


def test_reconcile_skips_index_md(db_path: Path, memory_root: Path):
    """index.md（vault 保留文件名）不应被索引。"""
    _write_item(memory_root, "a11.md", "01JZB0011")
    index_dir = memory_root / "items" / "vocab"
    index_dir.mkdir(parents=True, exist_ok=True)
    (index_dir / "index.md").write_text("---\ntitle: 语法索引\n---\n\n导航页\n", encoding="utf-8")
    conn = open_db(db_path)
    result = reconcile(conn, memory_root, "en")
    assert result.indexed == 1
    assert count_docs(conn) == 1
    rows = conn.execute("SELECT file_path FROM documents").fetchall()
    assert all("index.md" not in r[0] for r in rows)
