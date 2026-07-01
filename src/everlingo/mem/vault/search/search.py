# ref: docs/impl-spec/search/memory-vault-search-spec.md — 查询 API
# indexer 进程内的搜索实现，直接查 SQLite FTS5。
# query 先经 tokenize() 处理再 MATCH；snippet 走 body_raw UNINDEXED 干净原文。
# bm25 加权：headword / title 高权重。
#
# 本期只支持 mode='exact' (FTS)；mode='semantic' / 'hybrid' 接口已为
# 将来向量检索预留。

from __future__ import annotations

import logging
import sqlite3
import time
from typing import Literal

from .protocol import ChunkRef, SearchHit
from .tokenizer import tokenize_for_fts_query

logger = logging.getLogger(__name__)


# bm25 权重：headword, title, intro_iface, intro_target, aliases, related, tags, body
# 索引列顺序对应 documents_fts 定义：headword=1, title=2, intro_in_interface_lang=3,
# intro_in_target_lang=4, aliases=5, related=6, tags=7, body=8, body_raw=9(UNINDEXED)
# FTS5 bm25 多个权重用逗号分隔。
_BM25_WEIGHTS = "10.0, 10.0, 4.0, 4.0, 2.0, 2.0, 2.0, 1.0"


def search(
    conn: sqlite3.Connection,
    query: str,
    lang: str | None = None,
    item_type: str | None = None,
    tags: list[str] | None = None,
    kind: str | None = None,
    mode: Literal["exact", "semantic", "hybrid"] = "exact",
    limit: int = 20,
) -> list[SearchHit]:
    """执行 FTS5 检索；返回 SearchHit 列表。"""
    start = time.perf_counter()
    if mode != "exact":
        logger.warning("mode=%s 本期未实现，路由为 exact", mode)

    fts_q = tokenize_for_fts_query(query)
    if not fts_q:
        return []

    where_clauses = ["documents_fts MATCH ?"]
    where_params: list = [fts_q]

    if lang is not None:
        where_clauses.append("d.lang = ?")
        where_params.append(lang)
    if item_type is not None:
        where_clauses.append("d.item_type = ?")
        where_params.append(item_type)
    if kind is not None:
        where_clauses.append("d.kind = ?")
        where_params.append(kind)
    if tags:
        # tags 存 ' ' 连接，做 FTS 风格的 token 包含判定
        for t in tags:
            where_clauses.append("d.tags LIKE ?")
            where_params.append(f"%{t}%")

    sql = f"""
        SELECT d.rowid, d.ulid, d.kind, d.lang, d.item_type, d.file_path, d.title,
               snippet(documents_fts, 8, '【', '】', '…', 12) AS body_snippet,
               bm25(documents_fts, {_BM25_WEIGHTS}) AS rank_score
        FROM documents_fts f
        JOIN documents d ON d.rowid = f.rowid
        WHERE {' AND '.join(where_clauses)}
        ORDER BY rank_score
        LIMIT ?
    """
    where_params.append(limit)

    try:
        rows = conn.execute(sql, where_params).fetchall()
    except sqlite3.OperationalError as e:
        # 兜底：query 触发了 FTS5 语法错误时返回空
        logger.warning("FTS5 查询失败，忽略: %s (query=%r)", e, fts_q)
        return []

    took_ms = (time.perf_counter() - start) * 1000.0
    hits: list[SearchHit] = []
    for r in rows:
        rowid, ulid, kind_v, lang_v, item_type_v, file_path, title, snippet, score = r
        hits.append(
            SearchHit(
                ulid=ulid,
                kind=kind_v,
                lang=lang_v,
                item_type=item_type_v,
                file_path=file_path,
                title=title,
                score=float(score) if score is not None else 0.0,
                source="fts",
                chunk=None,
                snippet=snippet or "",
            )
        )
    logger.debug("search took %.2fms, hits=%d", took_ms, len(hits))
    return hits


def search_chunk(
    conn: sqlite3.Connection,
    query: str,
    doc_rowid: int,
    limit: int = 5,
) -> list[ChunkRef]:
    """对单文档的 chunks 做二次 FTS 检索（spec 未要求，本期预留）。"""
    fts_q = tokenize_for_fts_query(query)
    if not fts_q:
        return []
    # chunks.text 存原文，临时 tokenize 后用 FTS 表达式 LIKE 简单匹配
    # 本期不实现 chunk 级别 FTS（chunks 未建 FTS 虚拟表）。
    return []
