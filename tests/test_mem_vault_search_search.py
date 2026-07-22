# ref: docs/impl-spec/search/memory-vault-search-spec.md — 查询 API
# FTS 命中 / 字段过滤 / snippet 干净原文 / 混合 query 一致性。

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from everlingo.mem.vault.search import search as search_mod
from everlingo.mem.vault.search.indexer import (
    index_file,
    init_db,
    parse_file,
)
from everlingo.mem.vault.search.search import search as do_search


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
    init_db(c)
    yield c
    c.close()


def _write_item(memory_root: Path, name: str, ulid: str, type_: str, headword: str, title: str, body: str, lang: str = "en", tags: str = "", slug: str | None = None) -> Path:
    """写 kb item 文件。新布局：不含 {lang}/ 前缀。文件名即 {slug}.md。"""
    p = memory_root / "items" / type_ / name
    p.parent.mkdir(parents=True, exist_ok=True)
    if slug is None:
        slug = Path(name).stem
    fm = f"---\nulid: {ulid}\nslug: {slug}\ntype: {type_}\nheadword: {headword}\ntitle: {title}\n"
    if tags:
        fm += f"tags: {tags}\n"
    p.write_text(fm + f"---\n\n{body}", encoding="utf-8")
    return p


def test_search_exact_hit(conn: sqlite3.Connection, memory_root: Path):
    p = _write_item(
        memory_root, "computer--01JZA0001.md", "01JZA0001", "vocab", "computer", "计算机",
        "## 例句\nThis is a computer.\n## 解释\n硬件设备。",
    )
    index_file(conn, parse_file(p, memory_root, "en"))
    hits = do_search(conn, "computer", lang="en", limit=10)
    assert len(hits) == 1
    assert hits[0].ulid == "01JZA0001"
    assert hits[0].source == "fts"
    assert hits[0].score != 0.0
    # snippet 干净原文（包含原字符）
    assert "computer" in hits[0].snippet or "computer" in hits[0].title.lower() or "computer" in hits[0].title
    assert hits[0].lang == "en"


def test_search_field_filter_item_type(conn: sqlite3.Connection, memory_root: Path):
    p1 = _write_item(memory_root, "b4.md", "01JZA0004", "vocab", "banana", "香蕉", "fruit")
    p2 = _write_item(memory_root, "b5.md", "01JZA0005", "phrase", "banana republic", "香蕉共和国", "phrase")
    index_file(conn, parse_file(p1, memory_root, "en"))
    index_file(conn, parse_file(p2, memory_root, "en"))
    hits = do_search(conn, "banana", lang="en", item_type="phrase", limit=10)
    assert len(hits) == 1
    assert hits[0].ulid == "01JZA0005"


def test_search_no_match_returns_empty(conn: sqlite3.Connection, memory_root: Path):
    p = _write_item(memory_root, "c.md", "01JZA0006", "vocab", "cherry", "樱桃", "fruit")
    index_file(conn, parse_file(p, memory_root, "en"))
    hits = do_search(conn, "zzz_no_such_word", lang="en", limit=10)
    assert hits == []


def test_search_query_tokenize_consistency_zh(conn: sqlite3.Connection, memory_root: Path):
    """中文 query 与索引侧 tokenize 一致性：写入中文 title，query 用中文命中。"""
    p = _write_item(
        memory_root, "d--01JZA0007.md", "01JZA0007", "vocab", "自然", "自然语言处理",
        "## 解释\n研究语言与计算的学科。",
    )
    index_file(conn, parse_file(p, memory_root, "en"))
    hits = do_search(conn, "自然语言处理", lang="en", limit=10)
    assert len(hits) >= 1
    assert hits[0].ulid == "01JZA0007"


def test_search_kind_filter_event(conn: sqlite3.Connection, memory_root: Path):
    # 加一个 item
    p1 = _write_item(memory_root, "e.md", "01JZA0008", "vocab", "event", "事件", "x")
    index_file(conn, parse_file(p1, memory_root, "en"))
    # 加一个 events 文件（新布局：不含 {lang}/ 前缀）
    p2 = memory_root / "events" / "2026" / "06" / "2026-06-26.md"
    p2.parent.mkdir(parents=True, exist_ok=True)
    p2.write_text(
        "# 当天事件\n\n## Event\n- timestamp: 2026-06-26 10:00:00\n- headword: foo\n",
        encoding="utf-8",
    )
    index_file(conn, parse_file(p2, memory_root, "en"))
    hits = do_search(conn, "foo", lang="en", kind="event", limit=10)
    assert len(hits) >= 1
    assert hits[0].kind == "event"
    assert hits[0].lang == "en"


# ── tags 过滤 ─────────────────────────────────────────────────────


def test_search_tags_and(conn: sqlite3.Connection, memory_root: Path):
    p1 = _write_item(memory_root, "tag1.md", "01JZAT01", "vocab", "tag1", "T1",
                     "body", tags="[a, b]")
    p2 = _write_item(memory_root, "tag2.md", "01JZAT02", "vocab", "tag2", "T2",
                     "body", tags="[a]")
    index_file(conn, parse_file(p1, memory_root, "en"))
    index_file(conn, parse_file(p2, memory_root, "en"))
    hits = do_search(conn, "tag", lang="en", tags=["a", "b"], tags_op="and", limit=10)
    assert len(hits) == 1
    assert hits[0].ulid == "01JZAT01"


def test_search_tags_or(conn: sqlite3.Connection, memory_root: Path):
    p1 = _write_item(memory_root, "tag3.md", "01JZAT03", "vocab", "tag3", "T3",
                     "body", tags="[cats]")
    p2 = _write_item(memory_root, "tag4.md", "01JZAT04", "vocab", "tag4", "T4",
                     "body", tags="[dogs]")
    index_file(conn, parse_file(p1, memory_root, "en"))
    index_file(conn, parse_file(p2, memory_root, "en"))
    hits = do_search(conn, "tag", lang="en", tags=["cats", "dogs"], tags_op="or", limit=10)
    assert len(hits) == 2


def test_search_tags_exact_no_substring(conn: sqlite3.Connection, memory_root: Path):
    p1 = _write_item(memory_root, "tag5.md", "01JZAT05", "vocab", "tag5", "T5",
                     "body", tags="travel")
    p2 = _write_item(memory_root, "tag6.md", "01JZAT06", "vocab", "tag6", "T6",
                     "body", tags="traveling")
    index_file(conn, parse_file(p1, memory_root, "en"))
    index_file(conn, parse_file(p2, memory_root, "en"))
    hits = do_search(conn, "tag", lang="en", tags=["travel"], limit=10)
    assert len(hits) == 1
    assert hits[0].ulid == "01JZAT05"


def test_search_tags_empty_list_no_filter(conn: sqlite3.Connection, memory_root: Path):
    p1 = _write_item(memory_root, "tag7.md", "01JZAT07", "vocab", "tag7", "T7",
                     "body", tags="[z]")
    p2 = _write_item(memory_root, "tag8.md", "01JZAT08", "vocab", "tag8", "T8",
                     "body", tags="[z]")
    index_file(conn, parse_file(p1, memory_root, "en"))
    index_file(conn, parse_file(p2, memory_root, "en"))
    hits = do_search(conn, "tag", lang="en", tags=[], limit=10)
    assert len(hits) == 2


def test_search_tags_single_ignores_op(conn: sqlite3.Connection, memory_root: Path):
    p1 = _write_item(memory_root, "tag9.md", "01JZAT09", "vocab", "tag9", "T9",
                     "body", tags="[single]")
    index_file(conn, parse_file(p1, memory_root, "en"))
    hits_a = do_search(conn, "tag", lang="en", tags=["single"], tags_op="and", limit=10)
    hits_o = do_search(conn, "tag", lang="en", tags=["single"], tags_op="or", limit=10)
    assert len(hits_a) == 1
    assert len(hits_o) == 1


# ── Filter-only recall（q 为空） ────────────────────────────────────


def test_search_tag_only_no_query(conn: sqlite3.Connection, memory_root: Path):
    p1 = _write_item(memory_root, "fo1.md", "01JZFO01", "vocab", "foo1", "F1",
                     "body x", tags="[filter]")
    p2 = _write_item(memory_root, "fo2.md", "01JZFO02", "vocab", "foo2", "F2",
                     "body y", tags="[other]")
    p3 = _write_item(memory_root, "fo3.md", "01JZFO03", "vocab", "foo3", "F3",
                     "body z", tags="[filter, other]")
    for p in (p1, p2, p3):
        index_file(conn, parse_file(p, memory_root, "en"))
    hits = do_search(conn, "", lang="en", tags=["filter"], limit=10)
    assert len(hits) == 2
    ulids = {h.ulid for h in hits}
    assert "01JZFO01" in ulids
    assert "01JZFO03" in ulids
    for h in hits:
        assert h.source == "filter"


def test_search_empty_q_no_filter_returns_empty(conn: sqlite3.Connection, memory_root: Path):
    p = _write_item(memory_root, "ef.md", "01JZEF01", "vocab", "empty", "Empty",
                    "body", tags="[some]")
    index_file(conn, parse_file(p, memory_root, "en"))
    hits = do_search(conn, "", lang="en", limit=10)
    assert hits == []
