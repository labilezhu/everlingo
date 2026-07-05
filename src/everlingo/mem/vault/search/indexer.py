# ref: docs/impl-spec/search/memory-vault-search-spec.md — indexer / Schema DDL / Chunk 切分
# indexer 进程内对 .md 文件做解析、写 documents / documents_fts / chunks。
# 关键约束：
#   - 幂等 upsert（按 ulid / 合成键）
#   - content_hash 基于原文，跳过未变文件
#   - chunks.text 保留原文（向量嵌入用），不分词
#   - FTS 各列存分词后空格连接文本；body_raw 存原文供 snippet()
#   - chunks 单段 >800 字符时按段落/句号二次切，子 chunk 继承 section_title

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
import time
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Iterable

from . import events_index
from .events_index import parse_kb_item_path
from ..frontmatter import parse_frontmatter
from .tokenizer import tokenize, tokenizer_version

logger = logging.getLogger(__name__)


# ── 常量 ────────────────────────────────────────────────────────────


MAX_CHUNK_CHARS = 800  # spec §Chunk 切分策略：单 chunk 超阈值二次切


# ── frontmatter 解析 ────────────────────────────────────────────────
# 容错解析在 src/everlingo/mem/vault/frontmatter.py，本文件只通过
# `parse_frontmatter(text)` 调用。LLM Writer 偶尔写出近似但非法的 YAML
# （内嵌引号/冒号），由那里先 yaml.safe_load、失败回退逐行 key:value 解析。


@dataclass
class ParsedDoc:
    kind: str  # 'item' / 'event'
    item_type: str | None
    file_path: str  # 相对 lang vault 根（不含 {lang}/ 前缀）
    ulid: str
    slug: str | None
    headword: str | None
    title: str | None
    intro_in_interface_lang: str | None
    intro_in_target_lang: str | None
    aliases: str | None  # '\n' 连接
    related: str | None
    tags: str | None  # ' ' 连接
    first_seen: str | None
    last_seen: str | None
    seen_count: int | None
    schema_version: int | None
    body: str  # frontmatter 后的 markdown 原文
    file_mtime: str  # ISO 字符串
    content_hash: str


def _hash_content(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _mtime_iso(stat_mtime: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(stat_mtime))


def _join_newline(values) -> str:
    if not values:
        return ""
    if isinstance(values, str):
        return values
    return "\n".join(str(v) for v in values if v is not None and v != "")


def _join_space(values) -> str:
    if not values:
        return ""
    if isinstance(values, str):
        return values
    return " ".join(str(v) for v in values if v is not None and v != "")


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _resolve_rel(absolute: Path, memory_root: Path) -> str:
    rel = absolute.resolve().relative_to(memory_root.resolve()).as_posix()
    return rel


# ── 解析入口 ─────────────────────────────────────────────────────────


def parse_file(absolute: Path, memory_root: Path, lang: str) -> ParsedDoc:
    """解析单个 .md 文件为 ParsedDoc。lang 为 per-lang vault 的语言编码。"""
    rel = _resolve_rel(absolute, memory_root)
    stat = absolute.stat()
    text = absolute.read_text(encoding="utf-8")
    file_mtime = _mtime_iso(stat.st_mtime)
    content_hash = _hash_content(text)

    # events 文件特殊处理
    evt = events_index.parse_event_path(rel, lang)
    if evt is not None:
        # 整文件做 body；frontmatter 仍然解析（events 文件通常无 frontmatter）
        fm, body = parse_frontmatter(text)
        ulid = events_index.make_event_ulid(evt.lang, evt.date)
        return ParsedDoc(
            kind="event",
            item_type=None,
            file_path=rel,
            ulid=ulid,
            slug=None,
            headword=None,
            title=fm.get("title") or f"events {evt.date}",
            intro_in_interface_lang=fm.get("intro_in_interface_lang"),
            intro_in_target_lang=fm.get("intro_in_target_lang"),
            aliases=_join_newline(fm.get("aliases")),
            related=_join_newline(fm.get("related")),
            tags=_join_space(fm.get("tags")),
            first_seen=fm.get("first_seen"),
            last_seen=fm.get("last_seen"),
            seen_count=fm.get("seen_count"),
            schema_version=fm.get("schema_version"),
            body=body,
            file_mtime=file_mtime,
            content_hash=content_hash,
        )



    # kb item
    fm, body = parse_frontmatter(text)
    ulid = fm.get("ulid")
    if not ulid:
        raise ValueError(f"kb item 缺少 ulid frontmatter: {rel}")
    kb = parse_kb_item_path(rel, lang)
    if kb is None:
        logger.warning("kb item 路径不匹配 items/{type}/... 格式: %s", rel)
    return ParsedDoc(
        kind="item",
        item_type=fm.get("type"),
        file_path=rel,
        ulid=str(ulid),
        slug=fm.get("slug"),
        headword=fm.get("headword"),
        title=fm.get("title"),
        intro_in_interface_lang=fm.get("intro_in_interface_lang"),
        intro_in_target_lang=fm.get("intro_in_target_lang"),
        aliases=_join_newline(fm.get("aliases")),
        related=_join_newline(fm.get("related")),
        tags=_join_space(fm.get("tags")),
        first_seen=fm.get("first_seen"),
        last_seen=fm.get("last_seen"),
        seen_count=fm.get("seen_count"),
        schema_version=fm.get("schema_version"),
        body=body,
        file_mtime=file_mtime,
        content_hash=content_hash,
    )


# ── frontmatter chunks（仅 kind='item'）─────────────────────────────
# 每个文本内容 frontmatter 字段（headword / title /
# intro_in_interface_lang / intro_in_target_lang）生成一个 chunk，
# 供向量检索命中。数组字段（aliases/related/tags）跳过。
# 顺序固定，空值/缺失跳过；chunk_index 排在 body chunks 之前。

_FRONTMATTER_CHUNK_FIELDS: list[tuple[str, str | None]] = [
    ("headword", "headword"),
    ("title", "title"),
    ("intro_in_interface_lang", "intro_in_interface_lang"),
    ("intro_in_target_lang", "intro_in_target_lang"),
]


def _frontmatter_chunks(parsed: ParsedDoc) -> list[Chunk]:
    """为 kind='item' 的 frontmatter 文本内容字段生成 chunk 列表。

    chunk_index 从 0 开始；调用方在拼接 body chunks 时需顺延。
    """
    if parsed.kind != "item":
        return []
    out: list[Chunk] = []
    idx = 0
    for attr, label in _FRONTMATTER_CHUNK_FIELDS:
        value = getattr(parsed, attr, None)
        if not value:
            continue
        text = f"{label}: {value}"
        out.append(Chunk(
            chunk_index=idx,
            section_title=label,
            section_kind="frontmatter",
            text=text,
            char_offset=None,
            content_hash=_hash_content(text),
        ))
        idx += 1
    return out


# ── chunks 切分 ─────────────────────────────────────────────────────


@dataclass
class Chunk:
    chunk_index: int
    section_title: str | None
    section_kind: str | None
    text: str
    char_offset: int | None
    content_hash: str


_SECTION_HEADER_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.MULTILINE)
_SENTENCE_RE = re.compile(r"[^。！？\n]+[。！？\n]?")
_PARAGRAPH_RE = re.compile(r"\n\s*\n")


def _map_section_kind(title: str | None) -> str:
    if not title:
        return "section"
    t = title.strip()
    mapping = {
        "例句": "example",
        "给老师的例子": "example",
        "给老师的例句": "example",
        "例子": "example",
        "给我的解释": "explanation",
        "解释": "explanation",
        "记忆钩子": "memory_hook",
        "钩子": "memory_hook",
        "遇到记录": "encounter",
        "Event": "event",
        "event": "event",
    }
    return mapping.get(t, "section")


def _split_oversize(text: str) -> list[str]:
    """把超长文本按段落/句号二次切。"""
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    parts: list[str] = []
    for para in _PARAGRAPH_RE.split(text):
        para = para.strip()
        if not para:
            continue
        if len(para) <= MAX_CHUNK_CHARS:
            parts.append(para)
            continue
        # 按句号/感叹/问号切
        for sent in _SENTENCE_RE.findall(para):
            sent = sent.strip()
            if not sent:
                continue
            if len(sent) <= MAX_CHUNK_CHARS:
                parts.append(sent)
            else:
                # 仍超长，硬切
                for i in range(0, len(sent), MAX_CHUNK_CHARS):
                    parts.append(sent[i : i + MAX_CHUNK_CHARS])
    return parts


def split_chunks(body: str, kind: str) -> list[Chunk]:
    """按 markdown ## section 切 chunks；kind='event' 时委托 events_index.split_event_sections."""
    if kind == "event":
        sections = events_index.split_event_sections(body)
        chunks: list[Chunk] = []
        idx = 0
        for sec in sections:
            sub_texts = _split_oversize(sec.text)
            for sub in sub_texts:
                if not sub.strip():
                    continue
                chunks.append(
                    Chunk(
                        chunk_index=idx,
                        section_title=sec.title,
                        section_kind=sec.kind,
                        text=sub,
                        char_offset=sec.char_offset,
                        content_hash=_hash_content(sub),
                    )
                )
                idx += 1
        return chunks

    # 普通 kb item：按 ## section 切
    matches = list(_SECTION_HEADER_RE.finditer(body))
    if not matches:
        # 整 body 一段
        if not body.strip():
            return []
        chunks_list: list[Chunk] = []
        idx = 0
        for sub in _split_oversize(body):
            if not sub.strip():
                continue
            chunks_list.append(
                Chunk(
                    chunk_index=idx,
                    section_title=None,
                    section_kind="body",
                    text=sub,
                    char_offset=0,
                    content_hash=_hash_content(sub),
                )
            )
            idx += 1
        return chunks_list

    out: list[Chunk] = []
    idx = 0
    # preamble（在第一个 ## 之前）
    if matches[0].start() > 0:
        pre = body[: matches[0].start()]
        for sub in _split_oversize(pre):
            if not sub.strip():
                continue
            out.append(
                Chunk(
                    chunk_index=idx,
                    section_title=None,
                    section_kind="preamble",
                    text=sub,
                    char_offset=0,
                    content_hash=_hash_content(sub),
                )
            )
            idx += 1
    for i, m in enumerate(matches):
        title = m.group("title").strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        section_text = body[start:end]
        kind_mapped = _map_section_kind(title)
        for sub in _split_oversize(section_text):
            if not sub.strip():
                continue
            out.append(
                Chunk(
                    chunk_index=idx,
                    section_title=title,
                    section_kind=kind_mapped,
                    text=sub,
                    char_offset=start,
                    content_hash=_hash_content(sub),
                )
            )
            idx += 1
    return out


# ── DB 初始化 / 工具 ───────────────────────────────────────────────


def init_db(conn: sqlite3.Connection) -> None:
    """从 schema.sql 初始化数据库（已建表则跳过部分）。"""
    schema = resources.files("everlingo.mem.vault.search").joinpath("schema.sql").read_text(
        encoding="utf-8"
    )
    conn.executescript(schema)
    # 写分词器版本
    _set_meta(conn, "tokenizer_version", tokenizer_version())
    _set_meta(conn, "schema_version", "1")
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    _set_meta(conn, key, value)
    conn.commit()


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


# ── index_file / delete_file ───────────────────────────────────────


def _get_existing_rowid(conn: sqlite3.Connection, ulid: str) -> int | None:
    row = conn.execute("SELECT rowid FROM documents WHERE ulid=?", (ulid,)).fetchone()
    return row[0] if row else None


def _fts_text(value: str | None) -> str:
    if not value:
        return ""
    return tokenize(value)


def index_file(
    conn: sqlite3.Connection,
    parsed: ParsedDoc,
) -> int:
    """将 ParsedDoc 写入 documents + documents_fts + chunks（幂等 upsert）。

    Returns: documents.rowid.
    """
    existing = _get_existing_rowid(conn, parsed.ulid)
    indexed_at = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    if existing is None:
        cur = conn.execute(
            """
            INSERT INTO documents(
                ulid, kind, item_type, file_path, slug, headword, title,
                intro_in_interface_lang, intro_in_target_lang,
                aliases, related, tags,
                first_seen, last_seen, seen_count, schema_version,
                body, content_hash, file_mtime, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                parsed.ulid,
                parsed.kind,
                parsed.item_type,
                parsed.file_path,
                parsed.slug,
                parsed.headword,
                parsed.title,
                parsed.intro_in_interface_lang,
                parsed.intro_in_target_lang,
                parsed.aliases,
                parsed.related,
                parsed.tags,
                parsed.first_seen,
                parsed.last_seen,
                parsed.seen_count,
                parsed.schema_version,
                parsed.body,
                parsed.content_hash,
                parsed.file_mtime,
                indexed_at,
            ),
        )
        rowid = cur.lastrowid
    else:
        rowid = existing
        old_hash = conn.execute(
            "SELECT content_hash FROM documents WHERE rowid=?", (rowid,)
        ).fetchone()[0]
        if old_hash == parsed.content_hash:
            # 内容未变：仅刷新 mtime/索引时间与可变元数据(seen_count 等)；
            # 不动 chunks / FTS / embedding，保 chunk_id 稳定。
            conn.execute(
                """
                UPDATE documents SET
                    file_mtime=?, indexed_at=?,
                    seen_count=?, last_seen=?, first_seen=?
                WHERE rowid=?
                """,
                (
                    parsed.file_mtime,
                    indexed_at,
                    parsed.seen_count,
                    parsed.last_seen,
                    parsed.first_seen,
                    rowid,
                ),
            )
            conn.commit()
            logger.debug("index_file: content_hash 未变，跳过重建 ulid=%s", parsed.ulid)
            return rowid
        conn.execute(
            """
            UPDATE documents SET
                kind=?, item_type=?, file_path=?, slug=?, headword=?, title=?,
                intro_in_interface_lang=?, intro_in_target_lang=?,
                aliases=?, related=?, tags=?,
                first_seen=?, last_seen=?, seen_count=?, schema_version=?,
                body=?, content_hash=?, file_mtime=?, indexed_at=?
            WHERE rowid=?
            """,
            (
                parsed.kind,
                parsed.item_type,
                parsed.file_path,
                parsed.slug,
                parsed.headword,
                parsed.title,
                parsed.intro_in_interface_lang,
                parsed.intro_in_target_lang,
                parsed.aliases,
                parsed.related,
                parsed.tags,
                parsed.first_seen,
                parsed.last_seen,
                parsed.seen_count,
                parsed.schema_version,
                parsed.body,
                parsed.content_hash,
                parsed.file_mtime,
                indexed_at,
                rowid,
            ),
        )
        # chunks 与 FTS 行级联清理后重建
        conn.execute("DELETE FROM chunks WHERE doc_rowid=?", (rowid,))
        conn.execute("DELETE FROM documents_fts WHERE rowid=?", (rowid,))

    # FTS 行
    fts_headword = _fts_text(parsed.headword)
    fts_title = _fts_text(parsed.title)
    fts_intro_iface = _fts_text(parsed.intro_in_interface_lang)
    fts_intro_target = _fts_text(parsed.intro_in_target_lang)
    fts_aliases = _fts_text(parsed.aliases.replace("\n", " ") if parsed.aliases else "")
    fts_related = _fts_text(parsed.related.replace("\n", " ") if parsed.related else "")
    fts_tags = parsed.tags or ""
    fts_body = _fts_text(parsed.body)
    conn.execute(
        """
        INSERT INTO documents_fts(
            rowid, headword, title,
            intro_in_interface_lang, intro_in_target_lang,
            aliases, related, tags, body, body_raw
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rowid,
            fts_headword,
            fts_title,
            fts_intro_iface,
            fts_intro_target,
            fts_aliases,
            fts_related,
            fts_tags,
            fts_body,
            parsed.body,
        ),
    )

    # chunks：frontmatter 字段 chunk 在前，body chunk 在后
    fm_chunks = _frontmatter_chunks(parsed)
    body_chunks = split_chunks(parsed.body, parsed.kind)
    offset = len(fm_chunks)
    for c in body_chunks:
        c.chunk_index += offset
    all_chunks = fm_chunks + body_chunks
    for c in all_chunks:
        conn.execute(
            """
            INSERT INTO chunks(
                doc_rowid, chunk_index, section_title, section_kind,
                text, char_offset, content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (rowid, c.chunk_index, c.section_title, c.section_kind, c.text, c.char_offset, c.content_hash),
        )
    conn.commit()
    return rowid


def delete_file(conn: sqlite3.Connection, file_path: str) -> bool:
    """按 file_path 删除索引行（FTS / chunks 跟随 CASCADE）。

    Returns: 是否命中并删除。
    """
    cur = conn.execute("DELETE FROM documents WHERE file_path=?", (file_path,))
    conn.commit()
    return cur.rowcount > 0


def delete_by_ulid(conn: sqlite3.Connection, ulid: str) -> bool:
    cur = conn.execute("DELETE FROM documents WHERE ulid=?", (ulid,))
    conn.commit()
    return cur.rowcount > 0


def get_by_ulid(conn: sqlite3.Connection, ulid: str) -> tuple[int, str] | None:
    """按 ulid 查 (rowid, content_hash)；用于跳过未变文件。"""
    row = conn.execute(
        "SELECT rowid, content_hash FROM documents WHERE ulid=?", (ulid,)
    ).fetchone()
    if row is None:
        return None
    return (row[0], row[1])


def list_all_paths(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT file_path FROM documents").fetchall()
    return [r[0] for r in rows]


def count_docs(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]


def count_chunks(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]


def walk_vault(memory_root: Path) -> Iterable[Path]:
    """递归产出 memory_root 下所有 .md 文件（排除 tmp/ 子目录）。"""
    for p in memory_root.rglob("*.md"):
        if p.is_file() and "tmp" not in p.parts:
            yield p


def rebuild_fts(conn: sqlite3.Connection) -> int:
    """清空 FTS / chunks，用 documents.body 重新填充；不重读文件。

    tokenizer_version 变化时调用。returns: 重建行数。
    """
    rows = conn.execute("SELECT rowid, body FROM documents").fetchall()
    conn.execute("DELETE FROM documents_fts")
    conn.execute("DELETE FROM chunks")
    indexed = 0
    for rowid, body in rows:
        meta_row = conn.execute(
            "SELECT headword, title, intro_in_interface_lang, intro_in_target_lang, "
            "aliases, related, tags, kind FROM documents WHERE rowid=?",
            (rowid,),
        ).fetchone()
        if meta_row is None:
            continue
        headword, title, intro_iface, intro_target, aliases, related, tags, kind = meta_row
        conn.execute(
            "INSERT INTO documents_fts(rowid, headword, title, intro_in_interface_lang, "
            "intro_in_target_lang, aliases, related, tags, body, body_raw) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                rowid,
                _fts_text(headword),
                _fts_text(title),
                _fts_text(intro_iface),
                _fts_text(intro_target),
                _fts_text((aliases or "").replace("\n", " ")),
                _fts_text((related or "").replace("\n", " ")),
                tags or "",
                _fts_text(body),
                body,
            ),
        )
    # chunks 重建
    fm_fields = [(headword, "headword"), (title, "title"),
                 (intro_iface, "intro_in_interface_lang"),
                 (intro_target, "intro_in_target_lang")]
    fm_chunks: list[Chunk] = []
    if kind == "item":
        idx = 0
        for value, label in fm_fields:
            if not value:
                continue
            text = f"{label}: {value}"
            fm_chunks.append(Chunk(
                chunk_index=idx,
                section_title=label,
                section_kind="frontmatter",
                text=text,
                char_offset=None,
                content_hash=_hash_content(text),
            ))
            idx += 1
    body_chunks = split_chunks(body, kind)
    offset = len(fm_chunks)
    for c in body_chunks:
        c.chunk_index += offset
    for c in fm_chunks + body_chunks:
        conn.execute(
            "INSERT INTO chunks(doc_rowid, chunk_index, section_title, section_kind, "
            "text, char_offset, content_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (rowid, c.chunk_index, c.section_title, c.section_kind, c.text, c.char_offset, c.content_hash),
        )
    indexed += 1
    conn.commit()
    return indexed
