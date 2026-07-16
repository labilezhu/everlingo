# ref: docs/impl-spec/search/memory-vault-search-spec.md — Schema DDL / indexer
# 核心流程：
#   - init_db 建表 + 写 meta
#   - parse_file frontmatter / events 路径分发
#   - index_file 幂等 upsert（FTS 字段化分词入列，body_raw 原文）
#   - split_chunks：## section 切分 + 800 字符二次切
#   - delete_file / delete_by_ulid
#   - content_hash 跳过未变文件

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from everlingo.mem.vault.search import indexer
from everlingo.mem.vault.search.indexer import (
    count_chunks,
    count_docs,
    delete_by_ulid,
    delete_file,
    get_by_ulid,
    get_meta,
    index_file,
    init_db,
    parse_file,
    set_meta,
    split_chunks,
)


@pytest.fixture
def memory_root(tmp_path: Path) -> Path:
    root = tmp_path / "memory"
    root.mkdir()
    return root


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "index" / "memory.sqlite"


@pytest.fixture
def conn(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(db_path))
    c.execute("PRAGMA foreign_keys=ON")
    init_db(c)
    yield c
    c.close()


# ── init_db / meta ──────────────────────────────────────────────


def test_init_db_creates_tables(conn: sqlite3.Connection):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view') ORDER BY name"
    ).fetchall()
    names = {r[0] for r in rows}
    assert "documents" in names
    assert "documents_fts" in names
    assert "chunks" in names
    assert "chunk_embeddings" in names
    assert "meta" in names


def test_init_db_sets_meta(conn: sqlite3.Connection):
    assert get_meta(conn, "tokenizer_version") is not None
    assert get_meta(conn, "schema_version") == "3"


def test_set_meta_overwrites(conn: sqlite3.Connection):
    set_meta(conn, "k", "v1")
    set_meta(conn, "k", "v2")
    assert get_meta(conn, "k") == "v2"


# ── parse_file: kb item / events ────────────────────────


def _write_kb_item(memory_root: Path, name: str, front: dict, body: str = "正文") -> Path:
    """写 kb item 文件。新布局：相对 lang vault，不含 {lang}/ 前缀。"""
    p = memory_root / "items" / "vocab" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    fm_lines = ["---"]
    for k, v in front.items():
        fm_lines.append(f"{k}: {v}")
    fm_lines.append("---")
    p.write_text("\n".join(fm_lines) + "\n\n" + body, encoding="utf-8")
    return p


def test_parse_file_kb_item(memory_root: Path):
    p = _write_kb_item(
        memory_root,
        "aimai.md",
        {
            "ulid": "01JZABD123",
            "slug": "aimai",
            "type": "vocab",
            "headword": "aimai",
            "title": "あいまい",
        },
        body="# あいまい\n## 例句\nこれは例です。",
    )
    parsed = parse_file(p, memory_root, "en")
    assert parsed.kind == "item"
    assert parsed.ulid == "01JZABD123"
    assert parsed.item_type == "vocab"
    assert parsed.headword == "aimai"
    assert parsed.title == "あいまい"
    assert parsed.content_hash
    assert parsed.body.startswith("# あいまい")


def test_parse_file_kb_item_missing_ulid_raises(memory_root: Path):
    p = memory_root / "items" / "vocab" / "no-ulid.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\ntitle: x\n---\n\nbody", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_file(p, memory_root, "en")


def test_parse_file_events(memory_root: Path):
    p = memory_root / "events" / "2026" / "06" / "2026-06-26.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# 当天事件\n\n## Event\n", encoding="utf-8")
    parsed = parse_file(p, memory_root, "en")
    assert parsed.kind == "event"
    assert parsed.ulid == "event:en:2026-06-26"



# ── index_file: 幂等 upsert / FTS / chunks ─────────────────────


def test_index_file_inserts_doc_fts_chunks(conn: sqlite3.Connection, memory_root: Path):
    p = _write_kb_item(
        memory_root,
        "computer.md",
        {
            "ulid": "01JZABD789",
            "slug": "computer",
            "type": "vocab",
            "headword": "computer",
            "title": "计算机",
            "tags": "tech hardware",
        },
        body="## 例句\nThis is a computer.\n## 解释\n硬件设备。",
    )
    parsed = parse_file(p, memory_root, "en")
    rowid = index_file(conn, parsed)
    assert rowid > 0
    assert count_docs(conn) == 1
    assert count_chunks(conn) >= 1

    # 文档字段正确（lang 列已删除，不再验证）
    row = conn.execute(
        "SELECT ulid, kind, item_type, headword, title, tags FROM documents WHERE rowid=?",
        (rowid,),
    ).fetchone()
    assert row[0] == "01JZABD789"
    assert row[1] == "item"
    assert row[2] == "vocab"
    assert row[3] == "computer"
    assert row[4] == "计算机"
    assert row[5] == "tech hardware"

    # FTS 行存在
    fts_row = conn.execute("SELECT headword, body, body_raw FROM documents_fts WHERE rowid=?", (rowid,)).fetchone()
    assert fts_row is not None
    assert "computer" in fts_row[0]
    # body_raw 是原文（与 parsed.body 相同）
    assert fts_row[2] == parsed.body


def test_index_file_idempotent_no_change(conn: sqlite3.Connection, memory_root: Path):
    """content_hash 未变 → 重新 index_file 也不应改变 documents 行内容。"""
    p = _write_kb_item(
        memory_root,
        "x999.md",
        {"ulid": "01JZABD999", "slug": "x", "type": "vocab"},
        body="body",
    )
    parsed = parse_file(p, memory_root, "en")
    index_file(conn, parsed)
    index_file(conn, parsed)  # 二次 index
    assert count_docs(conn) == 1


def test_index_file_content_hash_short_circuit_preserves_chunks(
    conn: sqlite3.Connection, memory_root: Path
):
    """touch 未变内容 → chunk_id 保持不变，chunks 计数不变。"""
    p = _write_kb_item(
        memory_root,
        "y1ff.md",
        {"ulid": "01JZABD1FF", "slug": "y", "type": "vocab", "seen_count": 1},
        body="## 解释\noriginal body",
    )
    parsed = parse_file(p, memory_root, "en")
    index_file(conn, parsed)
    first_chunks = conn.execute(
        "SELECT chunk_id, section_kind FROM chunks ORDER BY chunk_id"
    ).fetchall()
    assert len(first_chunks) >= 1
    # 模拟 touch：mtime 变、seen_count 增，content_hash 不变
    parsed2 = parse_file(p, memory_root, "en")
    assert parsed2.content_hash == parsed.content_hash
    index_file(conn, parsed2)
    second_chunks = conn.execute(
        "SELECT chunk_id, section_kind FROM chunks ORDER BY chunk_id"
    ).fetchall()
    # chunk_id 完全一致（保 embedding 持久化）
    assert [c[0] for c in second_chunks] == [c[0] for c in first_chunks]
    # chunks 数量不变
    assert len(second_chunks) == len(first_chunks)
    # 但 mtime / indexed_at 应已更新
    new_mtime = conn.execute(
        "SELECT file_mtime FROM documents WHERE ulid=?", ("01JZABD1FF",)
    ).fetchone()[0]
    assert new_mtime == parsed2.file_mtime


def test_index_file_content_change_rebuilds_chunks(
    conn: sqlite3.Connection, memory_root: Path
):
    """content_hash 变了 → 走原 DELETE+重建路径，chunks 内容更新。"""
    p = _write_kb_item(
        memory_root,
        "z200.md",
        {"ulid": "01JZABD200", "slug": "z", "type": "vocab"},
        body="## 解释\nv1",
    )
    parsed = parse_file(p, memory_root, "en")
    index_file(conn, parsed)
    old_text = conn.execute(
        "SELECT text FROM chunks LIMIT 1"
    ).fetchone()[0]
    assert "v1" in old_text
    # 改内容
    p.write_text(
        "---\nulid: 01JZABD200\nslug: z\ntype: vocab\n---\n\n## 解释\nv2 body",
        encoding="utf-8",
    )
    parsed2 = parse_file(p, memory_root, "en")
    assert parsed2.content_hash != parsed.content_hash
    index_file(conn, parsed2)
    new_text = conn.execute(
        "SELECT text FROM chunks LIMIT 1"
    ).fetchone()[0]
    assert "v2" in new_text
    # documents.content_hash 也已更新
    h = conn.execute(
        "SELECT content_hash FROM documents WHERE ulid=?", ("01JZABD200",)
    ).fetchone()[0]
    assert h == parsed2.content_hash


def test_index_file_update_changes_hash(conn: sqlite3.Connection, memory_root: Path):
    p = _write_kb_item(
        memory_root,
        "x998.md",
        {"ulid": "01JZABD998", "slug": "x", "type": "vocab"},
        body="old",
    )
    parsed = parse_file(p, memory_root, "en")
    index_file(conn, parsed)
    p.write_text(
        "---\nulid: 01JZABD998\nslug: x\ntype: vocab\n---\n\nnew body content",
        encoding="utf-8",
    )
    parsed2 = parse_file(p, memory_root, "en")
    assert parsed2.content_hash != parsed.content_hash
    index_file(conn, parsed2)
    assert count_docs(conn) == 1
    assert get_by_ulid(conn, "01JZABD998")[1] == parsed2.content_hash


def test_index_file_events_kind_event_ulid(conn: sqlite3.Connection, memory_root: Path):
    p = memory_root / "events" / "2026" / "06" / "2026-06-26.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "# 当天事件\n\n## Event\n- chat_session_id: s1\n- entry_id: e1\n- timestamp: 2026-06-26 10:00:00\n- channel_name: stdio\n- item_type: vocab\n- why_want_to_save_memory: w\n- user_intent: i\n- lang: ja\n- headword: 曖昧\n\n### mean_summary\n意味がはっきりしない。\n",
        encoding="utf-8",
    )
    parsed = parse_file(p, memory_root, "ja")
    index_file(conn, parsed)
    assert count_docs(conn) == 1
    # FTS 行 kind='event'
    row = conn.execute("SELECT kind FROM documents WHERE ulid=?", (parsed.ulid,)).fetchone()
    assert row[0] == "event"


# ── delete_file / delete_by_ulid ────────────────────────────────


def test_delete_file_cascades_chunks(conn: sqlite3.Connection, memory_root: Path):
    p = _write_kb_item(
        memory_root,
        "x997.md",
        {"ulid": "01JZABD997", "slug": "x", "type": "vocab"},
        body="## 例句\nfoo",
    )
    parsed = parse_file(p, memory_root, "en")
    index_file(conn, parsed)
    assert count_chunks(conn) >= 1
    assert delete_file(conn, parsed.file_path) is True
    assert count_docs(conn) == 0
    assert count_chunks(conn) == 0


def test_delete_by_ulid(conn: sqlite3.Connection, memory_root: Path):
    p = _write_kb_item(
        memory_root,
        "x996.md",
        {"ulid": "01JZABD996", "slug": "x", "type": "vocab"},
        body="x",
    )
    parsed = parse_file(p, memory_root, "en")
    index_file(conn, parsed)
    assert delete_by_ulid(conn, "01JZABD996") is True
    assert count_docs(conn) == 0


# ── split_chunks ────────────────────────────────────────────────


def test_split_chunks_by_section():
    body = "preamble text\n\n## 例句\nThis is example.\n\n## 解释\nexplanation."
    chunks = split_chunks(body, "item")
    titles = [c.section_title for c in chunks]
    assert "例句" in titles
    assert "解释" in titles


def test_split_chunks_section_kind_mapping():
    body = "## 例句\na\n\n## 给我的解释\nb\n\n## 记忆钩子\nc"
    chunks = split_chunks(body, "item")
    kinds = {c.section_title: c.section_kind for c in chunks}
    assert kinds["例句"] == "example"
    assert kinds["给我的解释"] == "explanation"
    assert kinds["记忆钩子"] == "memory_hook"


def test_split_chunks_oversize_sub_split():
    """单段 >800 字符应按段落/句号二次切。"""
    long = "a。" * 500  # 1000 字符
    body = f"## 解释\n{long}"
    chunks = split_chunks(body, "item")
    # 二次切至少 2 段
    sec = [c for c in chunks if c.section_title == "解释"]
    assert len(sec) >= 2
    for c in sec:
        assert len(c.text) <= 800 or len(sec) == 1


def test_split_chunks_events_sections():
    body = "preamble\n\n## Event\nfoo\n\n## Event\nbar"
    chunks = split_chunks(body, "event")
    event_chunks = [c for c in chunks if c.section_kind == "event"]
    assert len(event_chunks) == 2
    assert "foo" in event_chunks[0].text
    assert "bar" in event_chunks[1].text


def test_split_chunks_empty_body_returns_empty():
    assert split_chunks("", "item") == []
    assert split_chunks("   \n  ", "item") == []


# ── parse_file: 容错 frontmatter（LLM Writer 写坏 case） ─────────


def _write_kb_item_raw(memory_root: Path, name: str, raw_fm: str, body: str = "body") -> Path:
    p = memory_root / "items" / "vocab" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{raw_fm}\n---\n\n{body}", encoding="utf-8")
    return p


def test_parse_file_tolerates_title_with_embedded_quotes(memory_root: Path):
    """log 真实 case: `title: "god" 释义`"""
    p = _write_kb_item_raw(
        memory_root,
        "god.md",
        'ulid: 01KWDV\ntype: vocab\nheadword: god\ntitle: "god" 释义',
    )
    parsed = parse_file(p, memory_root, "en")
    assert parsed.ulid == "01KWDV"
    assert parsed.title == '"god" 释义'
    assert parsed.kind == "item"


def test_parse_file_tolerates_intro_with_colon_in_value(memory_root: Path):
    """log 真实 case: `description_in_target_lang: ... "for" and "since": duration vs point in time`"""
    p = _write_kb_item_raw(
        memory_root,
        "xkwbs.md",
        (
            "ulid: 01KWBS\n"
            "type: grammar\n"
            'description_in_target_lang: The difference between "for" and "since": '
            "duration vs point in time"
        ),
    )
    parsed = parse_file(p, memory_root, "en")
    assert parsed.ulid == "01KWBS"
    assert "duration vs point in time" in parsed.description_in_target_lang


def test_parse_file_tolerates_intro_with_colon_before_quotes(memory_root: Path):
    """log 真实 case: `description_in_target_lang: Subject-verb agreement: "I" takes ...`"""
    p = _write_kb_item_raw(
        memory_root,
        "ykwb7.md",
        (
            "ulid: 01KWB7\n"
            "type: grammar\n"
            'description_in_target_lang: Subject-verb agreement: "I" takes the base '
            "form of the verb"
        ),
    )
    parsed = parse_file(p, memory_root, "en")
    assert parsed.ulid == "01KWB7"
    assert parsed.description_in_target_lang == (
        'Subject-verb agreement: "I" takes the base form of the verb'
    )



# ── frontmatter chunks ─────────────────────────────────────

from everlingo.mem.vault.search.indexer import _frontmatter_chunks, Chunk


def test_frontmatter_chunks_kind_item():
    """kind='item' 时 headword/title/description/description_in_target_lang 各生成一个 chunk。"""
    parsed = _make_parsed_doc(
        kind="item",
        headword="曖昧",
        title='"曖昧" 释义',
        description='"曖昧" 释义',
        description_in_target_lang="「曖昧」の定義",
    )
    chunks = _frontmatter_chunks(parsed)
    labels = [c.section_title for c in chunks]
    assert labels == ["headword", "title", "description", "description_in_target_lang"]
    for c in chunks:
        assert c.section_kind == "frontmatter"
        assert c.char_offset is None
        assert c.text.startswith(f"{c.section_title}: ")


def test_frontmatter_chunks_empty_fields_skipped():
    """空值/缺失字段不产生 chunk（如 pragmatics 无 headword）。"""
    parsed = _make_parsed_doc(
        kind="item",
        headword=None,
        title="语用学解释",
        description="语用学解释",
        description_in_target_lang="pragmatics explanation",
    )
    chunks = _frontmatter_chunks(parsed)
    labels = [c.section_title for c in chunks]
    assert "headword" not in labels
    assert "title" in labels


def test_frontmatter_chunks_not_for_events():
    parsed = _make_parsed_doc(kind="event")
    assert _frontmatter_chunks(parsed) == []



def test_index_file_frontmatter_chunks_prepended(conn: sqlite3.Connection, memory_root: Path):
    """index_file 写入的 chunks 中 frontmatter chunk 排在 body chunk 之前。"""
    p = _write_kb_item(
        memory_root,
        "aimai.md",
        {
            "ulid": "01JZABD123",
            "slug": "aimai",
            "type": "vocab",
            "headword": "曖昧",
            "title": "曖昧释义",
            "description": "曖昧释义",
            "description_in_target_lang": "aimai definition",
        },
        body="## 例句\nこれは例です。\n\n## 解释\n説明。",
    )
    parsed = parse_file(p, memory_root, "en")
    index_file(conn, parsed)
    rows = conn.execute(
        "SELECT chunk_index, section_kind, section_title, char_offset FROM chunks "
        "WHERE doc_rowid=(SELECT rowid FROM documents WHERE ulid=?) "
        "ORDER BY chunk_index",
        (parsed.ulid,),
    ).fetchall()
    # 前 4 个（或全部 frontmatter chunk）应为 frontmatter
    fm_rows = [r for r in rows if r[1] == "frontmatter"]
    body_rows = [r for r in rows if r[1] != "frontmatter"]
    assert len(fm_rows) == 4
    # frontmatter chunk_index 从 0 开始
    assert fm_rows[0][0] == 0
    # body chunk chunk_index 从 4 开始
    assert body_rows[0][0] == 4
    # char_offset 为 NULL（SQLite 返回 None）
    for r in fm_rows:
        assert r[3] is None


def test_index_file_frontmatter_chunks_content_hash_triggers_rebuild(
    conn: sqlite3.Connection, memory_root: Path
):
    """仅 frontmatter 改变（body 不变）→ content_hash 变 → chunks 重建。"""
    p = _write_kb_item(
        memory_root,
        "x300.md",
        {
            "ulid": "01JZABD300",
            "slug": "x",
            "type": "vocab",
            "headword": "old",
            "title": "old",
        },
        body="## 解释\nbody",
    )
    parsed = parse_file(p, memory_root, "en")
    index_file(conn, parsed)
    old_chunk_texts = {
        r[0] for r in conn.execute("SELECT text FROM chunks").fetchall()
    }
    # 改 frontmatter title
    p.write_text(
        "---\nulid: 01JZABD300\nslug: x\ntype: vocab\n"
        "headword: old\ntitle: new title\n---\n\n## 解释\nbody",
        encoding="utf-8",
    )
    parsed2 = parse_file(p, memory_root, "en")
    assert parsed2.content_hash != parsed.content_hash
    index_file(conn, parsed2)
    new_chunk_texts = {
        r[0] for r in conn.execute("SELECT text FROM chunks").fetchall()
    }
    # frontmatter chunk 中应有 'title: new title'
    assert any("new title" in t for t in new_chunk_texts)


def test_rebuild_fts_includes_frontmatter_chunks(conn: sqlite3.Connection, memory_root: Path):
    """rebuild_fts 重建的 chunks 也含 frontmatter chunk。"""
    p = _write_kb_item(
        memory_root,
        "x301.md",
        {
            "ulid": "01JZABD301",
            "slug": "x",
            "type": "vocab",
            "headword": "foo",
            "title": "bar",
            "description": "bar",
            "description_in_target_lang": "bar target",
        },
        body="## 例句\nexample",
    )
    parsed = parse_file(p, memory_root, "en")
    index_file(conn, parsed)
    # 触发 rebuild_fts（通过改 tokenizer_version 或直接调）
    from everlingo.mem.vault.search.indexer import rebuild_fts
    rebuild_fts(conn)
    rows = conn.execute(
        "SELECT section_kind, section_title FROM chunks "
        "WHERE doc_rowid=(SELECT rowid FROM documents WHERE ulid=?) "
        "ORDER BY chunk_index",
        ("01JZABD301",),
    ).fetchall()
    fm = [r for r in rows if r[0] == "frontmatter"]
    assert len(fm) == 4


# ── helpers ────────────────────────────────────────────────

def _make_parsed_doc(
    kind: str,
    headword=None,
    title=None,
    description=None,
    description_in_target_lang=None,
    item_type=None,
):
    """构造最小 ParsedDoc 用于 _frontmatter_chunks 测试。"""
    from everlingo.mem.vault.search.indexer import ParsedDoc
    return ParsedDoc(
        kind=kind,
        item_type=item_type,
        file_path="dummy.md",
        ulid="test-ulid",
        slug=None,
        headword=headword,
        title=title,
        description=description,
        description_in_target_lang=description_in_target_lang,
        aliases=None,
        related=None,
        tags=None,
        tag_list=[],
        first_seen=None,
        last_seen=None,
        seen_count=None,
        schema_version=None,
        body="",
        file_mtime="2026-01-01T00:00:00",
        content_hash="dummy",
    )


# ── document_tags ──────────────────────────────────────────────────


def _count_doc_tags(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    rows = conn.execute(
        "SELECT dt.tag, COUNT(*) FROM document_tags dt GROUP BY dt.tag ORDER BY dt.tag"
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def test_index_file_populates_document_tags(conn: sqlite3.Connection, memory_root: Path):
    p = _write_kb_item(
        memory_root,
        "t1.md",
        {"ulid": "01JZATAG1", "slug": "t1", "type": "vocab", "headword": "foo",
         "tags": ["adjective", "confusing"]},
    )
    parsed = parse_file(p, memory_root, "en")
    index_file(conn, parsed)
    tags = _count_doc_tags(conn)
    assert ("adjective", 1) in tags
    assert ("confusing", 1) in tags
    assert len(tags) == 2


def test_index_file_upsert_replaces_tags(conn: sqlite3.Connection, memory_root: Path):
    p = _write_kb_item(
        memory_root,
        "t2.md",
        {"ulid": "01JZATAG2", "slug": "t2", "type": "vocab", "headword": "bar",
         "tags": ["a", "b"]},
    )
    index_file(conn, parse_file(p, memory_root, "en"))
    assert len(_count_doc_tags(conn)) == 2

    # 改 tags 后重索引
    p2 = _write_kb_item(
        memory_root,
        "t2.md",
        {"ulid": "01JZATAG2", "slug": "t2", "type": "vocab", "headword": "bar",
         "tags": ["b", "c"]},
    )
    index_file(conn, parse_file(p2, memory_root, "en"))
    tags = _count_doc_tags(conn)
    assert ("b", 1) in tags
    assert ("c", 1) in tags
    # "a" 被清除
    assert ("a", 1) not in tags
    assert len(tags) == 2


def test_index_file_no_tags_empty_table(conn: sqlite3.Connection, memory_root: Path):
    p = _write_kb_item(
        memory_root,
        "t3.md",
        {"ulid": "01JZATAG3", "slug": "t3", "type": "vocab", "headword": "baz"},
    )
    index_file(conn, parse_file(p, memory_root, "en"))
    assert len(_count_doc_tags(conn)) == 0


def test_delete_file_cascades_document_tags(conn: sqlite3.Connection, memory_root: Path):
    p = _write_kb_item(
        memory_root,
        "t4.md",
        {"ulid": "01JZATAG4", "slug": "t4", "type": "vocab", "headword": "qux",
         "tags": ["delete_me"]},
    )
    parsed = parse_file(p, memory_root, "en")
    index_file(conn, parsed)
    assert len(_count_doc_tags(conn)) == 1
    delete_file(conn, parsed.file_path)
    assert len(_count_doc_tags(conn)) == 0


def test_open_db_ensures_document_tags_table_on_legacy_db(tmp_path: Path):
    """模拟旧库（不带 document_tags），open_db 应补建但不回填。"""
    from everlingo.mem.vault.search.sync import open_db

    db_path = tmp_path / "legacy" / "memory.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")
    # 手动创建 v2 库（无 document_tags 表）
    conn.executescript("""
        CREATE TABLE documents (
          rowid INTEGER PRIMARY KEY,
          ulid TEXT UNIQUE,
          kind TEXT NOT NULL,
          item_type TEXT,
          file_path TEXT NOT NULL UNIQUE,
          slug TEXT, headword TEXT, title TEXT,
          description TEXT, description_in_target_lang TEXT,
          aliases TEXT, related TEXT, tags TEXT,
          first_seen TEXT, last_seen TEXT,
          seen_count INTEGER, schema_version INTEGER,
          body TEXT NOT NULL, content_hash TEXT NOT NULL,
          file_mtime TEXT NOT NULL, indexed_at TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE documents_fts USING fts5(
          headword, title, description, description_in_target_lang,
          aliases, related, tags, body, body_raw UNINDEXED,
          tokenize='unicode61'
        );
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta(key, value) VALUES ('schema_version', '2');
        INSERT INTO meta(key, value) VALUES ('tokenizer_version', 'old');
    """)
    conn.close()
    # open_db 应补建 document_tags
    conn2 = open_db(db_path)
    try:
        t = conn2.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='document_tags'"
        ).fetchone()
        assert t is not None, "document_tags 表应被补建"
        ver = conn2.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
        assert ver == "3"
    finally:
        conn2.close()
