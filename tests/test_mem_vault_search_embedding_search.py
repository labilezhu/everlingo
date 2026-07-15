# ref: docs/impl-spec/search/memory-vault-embedding-spec.md — 向量召回 + RRF
# mode='semantic' / mode='hybrid' 行为；RRF 去重；source 字段。

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import sqlite_vec

from everlingo.mem.vault.search import search as search_mod
from everlingo.mem.vault.search.embedding import store
from everlingo.mem.vault.search.indexer import (
    index_file,
    init_db,
    parse_file,
)
from everlingo.mem.vault.search.search import search as do_search


DIM = 4


def _fake_vec(text: str, dim: int = DIM) -> list[float]:
    import hashlib

    h = hashlib.sha256(text.encode("utf-8")).digest()
    raw = [b / 255.0 - 0.5 for b in h[:dim]]
    norm = sum(x * x for x in raw) ** 0.5 or 1.0
    return [x / norm for x in raw]


class FakeEmbedder:
    def __init__(self, dim: int = DIM) -> None:
        self.dim = dim
        self.embed_calls = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.embed_calls += 1
        return [_fake_vec(t, self.dim) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return _fake_vec(text, self.dim)


def _load_vec0(conn: sqlite3.Connection) -> None:
    conn.enable_load_extension(True)
    conn.load_extension(sqlite_vec.loadable_path())
    conn.enable_load_extension(False)


@pytest.fixture
def memory_root(tmp_path: Path) -> Path:
    root = tmp_path / "memory"
    root.mkdir()
    return root


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "index" / "memory.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(db_path))
    c.execute("PRAGMA foreign_keys=ON")
    _load_vec0(c)
    init_db(c)
    store.set_current_model(c, "m", DIM)
    store.ensure_vec_table(c, DIM)
    yield c
    c.close()


def _write_item(memory_root: Path, name: str, ulid: str, type_: str, headword: str, title: str, body: str, tags: str = "") -> Path:
    """写 kb item 文件。新布局：不含 {lang}/ 前缀。"""
    p = memory_root / "items" / type_ / name
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = f"---\nulid: {ulid}\nslug: {name.split('--')[0]}\ntype: {type_}\nheadword: {headword}\ntitle: {title}\n"
    if tags:
        fm += f"tags: {tags}\n"
    p.write_text(fm + f"---\n\n{body}", encoding="utf-8")
    return p


def _index_and_embed(conn, memory_root, items):
    """index_file + 嵌入所有 chunks。"""
    for (name, ulid, type_, headword, title, body) in items:
        p = _write_item(memory_root, name, ulid, type_, headword, title, body)
        index_file(conn, parse_file(p, memory_root, "en"))
    # 取所有 chunk
    rows = conn.execute("SELECT chunk_id, text FROM chunks").fetchall()
    chunk_texts = [(r[0], r[1]) for r in rows]
    emb = FakeEmbedder()
    store.batch_upsert(conn, chunk_texts, emb, model_id="m", dim=DIM)
    conn.commit()
    return emb


# ── semantic mode ───────────────────────────────────────────────


def test_semantic_returns_vec_source_and_chunk(conn, memory_root):
    _index_and_embed(conn, memory_root, [
        ("a--01JZS0001.md", "01JZS0001", "vocab", "apple", "苹果",
         "## 解释\nred fruit"),
    ])
    emb = FakeEmbedder()
    hits = do_search(conn, "apple", lang="en", embedder=emb, mode="semantic", limit=10)
    assert len(hits) >= 1
    for h in hits:
        assert h.source == "vec"
        assert h.chunk is not None
        assert h.chunk.text
        assert h.score > 0
        assert h.lang == "en"
    # 全部来自同一文档
    assert all(h.ulid == hits[0].ulid for h in hits)


def test_semantic_no_embedder_returns_empty(conn, memory_root):
    """embedder=None 时 mode=semantic 返回空（不退化到 FTS）。"""
    _index_and_embed(conn, memory_root, [
        ("a--01JZS0004.md", "01JZS0004", "vocab", "apple", "苹果", "fruit"),
    ])
    hits = do_search(conn, "apple", lang="en", embedder=None, mode="semantic", limit=10)
    assert hits == []


def test_semantic_empty_index_returns_empty(conn, memory_root):
    emb = FakeEmbedder()
    hits = do_search(conn, "anything", lang="en", embedder=emb, mode="semantic", limit=10)
    assert hits == []


# ── hybrid mode + RRF ───────────────────────────────────────────


def test_hybrid_uses_rrf_and_marks_source(conn, memory_root):
    _index_and_embed(conn, memory_root, [
        ("a--01JZH0001.md", "01JZH0001", "vocab", "apple", "苹果", "fruit"),
    ])
    emb = FakeEmbedder()
    hits = do_search(conn, "apple", lang="en", embedder=emb, mode="hybrid", limit=10)
    assert len(hits) >= 1
    # 全部标 source='hybrid'
    assert all(h.source == "hybrid" for h in hits)
    # score > 0（RRF 加权）
    assert all(h.score > 0 for h in hits)


def test_hybrid_rrf_dedups_within_each_source(conn, memory_root):
    """同源内 RRF 去重：FTS ulid 唯一，vec (ulid, chunk_id) 唯一。"""
    _index_and_embed(conn, memory_root, [
        ("a--01JZH0002.md", "01JZH0002", "vocab", "apple", "苹果", "fruit"),
    ])
    emb = FakeEmbedder()
    hits = do_search(conn, "apple", lang="en", embedder=emb, mode="hybrid", limit=10)
    # FTS 来源：1 条（ulid=01JZH0002）
    fts_hits = [h for h in hits if h.chunk is None]
    assert len(fts_hits) == 1
    # vec 来源：文档 01JZH0002 的多个 chunk（headword / title / body）
    vec_hits = [h for h in hits if h.chunk is not None]
    assert len(vec_hits) >= 1
    assert all(h.ulid == "01JZH0002" for h in vec_hits)
    # 全部 source='hybrid'，全部 score > 0
    assert all(h.source == "hybrid" and h.score > 0 for h in hits)


def test_hybrid_no_embedder_falls_back_to_fts(conn, memory_root):
    """hybrid + embedder=None → 退化为 exact 路径。"""
    _index_and_embed(conn, memory_root, [
        ("a--01JZH0004.md", "01JZH0004", "vocab", "apple", "苹果", "fruit"),
    ])
    hits = do_search(conn, "apple", lang="en", embedder=None, mode="hybrid", limit=10)
    assert len(hits) == 1
    # 退化到 FTS，但走的是 hybrid 入口 → source 应为 'fts'（_fts_recall 填的）
    assert hits[0].source == "fts"
    assert hits[0].lang == "en"


# ── semantic + tags 过滤 ──────────────────────────────────────────


def _write_and_embed(conn, memory_root, name, ulid, type_, headword, title, body, tags=""):
    """写 item + index + 仅嵌入该文件的 chunks。"""
    p = _write_item(memory_root, name, ulid, type_, headword, title, body, tags=tags)
    parsed = parse_file(p, memory_root, "en")
    rowid = index_file(conn, parsed)
    doc_rowid = conn.execute("SELECT rowid FROM documents WHERE ulid=?", (ulid,)).fetchone()[0]
    rows = conn.execute(
        "SELECT chunk_id, text FROM chunks WHERE doc_rowid=?", (doc_rowid,)
    ).fetchall()
    chunk_texts = [(r[0], r[1]) for r in rows]
    emb = FakeEmbedder()
    store.batch_upsert(conn, chunk_texts, emb, model_id="m", dim=DIM)
    conn.commit()
    return emb


def test_vec_tags_filter_exact(conn, memory_root):
    """vec 路径 tag 精确匹配：travel 不命中 traveling。"""
    _write_and_embed(conn, memory_root,
        "vt1--01JZVT01.md", "01JZVT01", "vocab", "vt1", "VT1", "body a", tags="travel")
    _write_and_embed(conn, memory_root,
        "vt2--01JZVT02.md", "01JZVT02", "vocab", "vt2", "VT2", "body b", tags="traveling")
    emb = FakeEmbedder()
    hits = do_search(conn, "vt", lang="en", embedder=emb, mode="semantic",
                     tags=["travel"], limit=10)
    assert len(hits) >= 1
    assert all(h.ulid == "01JZVT01" for h in hits)


def test_vec_tags_or(conn, memory_root):
    """vec 路径 tags_op='or'。"""
    _write_and_embed(conn, memory_root,
        "vt3--01JZVT03.md", "01JZVT03", "vocab", "vt3", "VT3", "body x", tags="[cats]")
    _write_and_embed(conn, memory_root,
        "vt4--01JZVT04.md", "01JZVT04", "vocab", "vt4", "VT4", "body y", tags="[dogs]")
    emb = FakeEmbedder()
    hits = do_search(conn, "vt", lang="en", embedder=emb, mode="semantic",
                     tags=["cats", "dogs"], tags_op="or", limit=10)
    ulids = {h.ulid for h in hits}
    assert "01JZVT03" in ulids
    assert "01JZVT04" in ulids
