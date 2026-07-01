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


def _write_item(memory_root: Path, name: str, ulid: str, type_: str, headword: str, title: str, body: str, lang: str = "en", tags: str = "") -> Path:
    p = memory_root / lang / "items" / type_ / name
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = f"---\nulid: {ulid}\nslug: {name.split('--')[0]}\ntype: {type_}\nheadword: {headword}\ntitle: {title}\nlang: {lang}\n"
    if tags:
        fm += f"tags: {tags}\n"
    p.write_text(fm + f"---\n\n{body}", encoding="utf-8")
    return p


def test_search_exact_hit(conn: sqlite3.Connection, memory_root: Path):
    p = _write_item(
        memory_root, "computer--01JZA0001.md", "01JZA0001", "vocab", "computer", "计算机",
        "## 例句\nThis is a computer.\n## 解释\n硬件设备。",
    )
    index_file(conn, parse_file(p, memory_root))
    hits = do_search(conn, "computer", limit=10)
    assert len(hits) == 1
    assert hits[0].ulid == "01JZA0001"
    assert hits[0].source == "fts"
    assert hits[0].score != 0.0
    # snippet 干净原文（包含原字符）
    assert "computer" in hits[0].snippet or "computer" in hits[0].title.lower() or "computer" in hits[0].title


def test_search_field_filter_lang(conn: sqlite3.Connection, memory_root: Path):
    p1 = _write_item(memory_root, "a--01JZA0002.md", "01JZA0002", "vocab", "apple", "苹果", "fruit", lang="en")
    p2 = _write_item(memory_root, "a--01JZA0003.md", "01JZA0003", "vocab", "apple", "りんご", "fruit", lang="ja")
    index_file(conn, parse_file(p1, memory_root))
    index_file(conn, parse_file(p2, memory_root))
    hits = do_search(conn, "apple", lang="ja", limit=10)
    assert len(hits) == 1
    assert hits[0].ulid == "01JZA0003"


def test_search_field_filter_item_type(conn: sqlite3.Connection, memory_root: Path):
    p1 = _write_item(memory_root, "b--01JZA0004.md", "01JZA0004", "vocab", "banana", "香蕉", "fruit")
    p2 = _write_item(memory_root, "b--01JZA0005.md", "01JZA0005", "phrase", "banana republic", "香蕉共和国", "phrase")
    index_file(conn, parse_file(p1, memory_root))
    index_file(conn, parse_file(p2, memory_root))
    hits = do_search(conn, "banana", item_type="phrase", limit=10)
    assert len(hits) == 1
    assert hits[0].ulid == "01JZA0005"


def test_search_no_match_returns_empty(conn: sqlite3.Connection, memory_root: Path):
    p = _write_item(memory_root, "c--01JZA0006.md", "01JZA0006", "vocab", "cherry", "樱桃", "fruit")
    index_file(conn, parse_file(p, memory_root))
    hits = do_search(conn, "zzz_no_such_word", limit=10)
    assert hits == []


def test_search_query_tokenize_consistency_zh(conn: sqlite3.Connection, memory_root: Path):
    """中文 query 与索引侧 tokenize 一致性：写入中文 title，query 用中文命中。"""
    p = _write_item(
        memory_root, "d--01JZA0007.md", "01JZA0007", "vocab", "自然", "自然语言处理",
        "## 解释\n研究语言与计算的学科。",
    )
    index_file(conn, parse_file(p, memory_root))
    hits = do_search(conn, "自然语言处理", limit=10)
    assert len(hits) >= 1
    assert hits[0].ulid == "01JZA0007"


def test_search_kind_filter_event(conn: sqlite3.Connection, memory_root: Path):
    # 加一个 item
    p1 = _write_item(memory_root, "e--01JZA0008.md", "01JZA0008", "vocab", "event", "事件", "x")
    index_file(conn, parse_file(p1, memory_root))
    # 加一个 events 文件
    p2 = memory_root / "en" / "events" / "2026" / "06" / "2026-06-26.md"
    p2.parent.mkdir(parents=True, exist_ok=True)
    p2.write_text(
        "# 当天事件\n\n## Event\n- timestamp: 2026-06-26 10:00:00\n- lang: en\n- headword: foo\n",
        encoding="utf-8",
    )
    index_file(conn, parse_file(p2, memory_root))
    hits = do_search(conn, "foo", kind="event", limit=10)
    assert len(hits) >= 1
    assert hits[0].kind == "event"
