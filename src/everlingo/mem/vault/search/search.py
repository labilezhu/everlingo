# ref: docs/impl-spec/search/memory-vault-search-spec.md — 查询 API
# ref: docs/impl-spec/search/memory-vault-embedding-spec.md — 向量召回 + RRF
# indexer 进程内的搜索实现，直接查 SQLite。
# - mode='exact':  FTS5（unicode61 + 预分词，bm25 加权）
# - mode='semantic': chunk_vec KNN 召回（sqlite-vec）
# - mode='hybrid': FTS 召回 + KNN 召回 + RRF 融合
#
# FTS 侧：query 先经 tokenize() 处理再 MATCH；snippet 走 body_raw UNINDEXED 干净原文。
# bm25 加权：headword / title 高权重。
# 降级：sqlite-vec 扩展未加载 / OPENAI_EMBEDDING_MODEL 未配 → semantic/hybrid
# 返回空 + warning；FTS 不受影响。

from __future__ import annotations

import logging
import sqlite3
import time
from typing import Literal

from .embedding import store
from .protocol import ChunkRef, SearchHit
from .tokenizer import tokenize_for_fts_query

logger = logging.getLogger(__name__)


# bm25 权重：headword, title, intro_iface, intro_target, aliases, related, tags, body
# 索引列顺序对应 documents_fts 定义：headword=1, title=2, intro_in_interface_lang=3,
# intro_in_target_lang=4, aliases=5, related=6, tags=7, body=8, body_raw=9(UNINDEXED)
# FTS5 bm25 多个权重用逗号分隔。
_BM25_WEIGHTS = "10.0, 10.0, 4.0, 4.0, 2.0, 2.0, 2.0, 1.0"

# RRF 常数（k=60 为经典值，平衡高/低排位贡献）
_RRF_K = 60


def search(
    conn: sqlite3.Connection,
    query: str,
    *,
    embedder: store.Embedder | None = None,
    lang: str | None = None,
    item_type: str | None = None,
    tags: list[str] | None = None,
    kind: str | None = None,
    mode: Literal["exact", "semantic", "hybrid"] = "exact",
    limit: int = 20,
) -> list[SearchHit]:
    """三模式搜索入口。"""
    start = time.perf_counter()
    if mode == "exact":
        return _fts_recall(conn, query, lang, item_type, tags, kind, limit)
    if mode == "semantic":
        if embedder is None:
            logger.warning("mode=semantic 但 embedder 未提供，返回空")
            return []
        return _vec_recall(conn, embedder, query, lang, item_type, tags, kind, limit)
    if mode == "hybrid":
        if embedder is None:
            logger.warning("mode=hybrid 但 embedder 未提供，回退 exact")
            return _fts_recall(conn, query, lang, item_type, tags, kind, limit)
        return _hybrid_recall(
            conn, embedder, query, lang, item_type, tags, kind, limit
        )
    logger.warning("未知 mode=%s，回退 exact", mode)
    return _fts_recall(conn, query, lang, item_type, tags, kind, limit)


# ── FTS 召回 ────────────────────────────────────────────────────────


def _fts_recall(
    conn: sqlite3.Connection,
    query: str,
    lang: str | None,
    item_type: str | None,
    tags: list[str] | None,
    kind: str | None,
    limit: int,
) -> list[SearchHit]:
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
        logger.warning("FTS5 查询失败，忽略: %s (query=%r)", e, fts_q)
        return []

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
    return hits


# ── 向量召回 ────────────────────────────────────────────────────────


def _vec_recall(
    conn: sqlite3.Connection,
    embedder: store.Embedder,
    query: str,
    lang: str | None,
    item_type: str | None,
    tags: list[str] | None,
    kind: str | None,
    limit: int,
) -> list[SearchHit]:
    if not store.has_vec_table(conn):
        logger.warning("chunk_vec 不存在，semantic 模式不可用")
        return []
    try:
        qvec = embedder.embed_query(query)
    except Exception as e:
        logger.warning("embed_query 失败: %s", e)
        return []

    knn = store.knn_with_filter(
        conn, qvec, k=limit, lang=lang, item_type=item_type, kind=kind, tags=tags
    )
    if not knn:
        return []

    # join chunks + documents 取元数据
    chunk_ids = [cid for cid, _ in knn]
    placeholders = ",".join("?" * len(chunk_ids))
    rows = conn.execute(
        f"""
        SELECT c.chunk_id, c.section_title, c.section_kind, c.char_offset, c.text,
               d.ulid, d.kind, d.lang, d.item_type, d.file_path, d.title
        FROM chunks c JOIN documents d ON d.rowid = c.doc_rowid
        WHERE c.chunk_id IN ({placeholders})
        """,
        chunk_ids,
    ).fetchall()
    meta = {r[0]: r for r in rows}

    # cosine distance: 0=相同，2=相反；转 similarity = 1 - distance/2
    out: list[SearchHit] = []
    for cid, dist in knn:
        if cid not in meta:
            continue
        (
            _,
            section_title,
            section_kind,
            char_offset,
            text,
            ulid,
            kind_v,
            lang_v,
            item_type_v,
            file_path,
            title,
        ) = meta[cid]
        similarity = max(0.0, 1.0 - dist / 2.0)
        snippet = text[:120] + ("…" if len(text) > 120 else "")
        out.append(
            SearchHit(
                ulid=ulid,
                kind=kind_v,
                lang=lang_v,
                item_type=item_type_v,
                file_path=file_path,
                title=title,
                score=similarity,
                source="vec",
                chunk=ChunkRef(
                    chunk_id=cid,
                    section_title=section_title,
                    section_kind=section_kind,
                    char_offset=char_offset or 0,
                    text=text,
                ),
                snippet=snippet,
            )
        )
    return out


# ── Hybrid：FTS + Vec + RRF ────────────────────────────────────────


def _hybrid_recall(
    conn: sqlite3.Connection,
    embedder: store.Embedder,
    query: str,
    lang: str | None,
    item_type: str | None,
    tags: list[str] | None,
    kind: str | None,
    limit: int,
) -> list[SearchHit]:
    # 各自多取一些给 RRF 留融合空间
    over = max(limit * 2, 20)
    fts_hits = _fts_recall(conn, query, lang, item_type, tags, kind, over)
    vec_hits = _vec_recall(conn, embedder, query, lang, item_type, tags, kind, over)

    fused = _rrf_fuse(fts_hits, vec_hits, limit=limit)
    # 标 source='hybrid'
    for h in fused:
        h.source = "hybrid"
    return fused


def _rrf_fuse(
    fts_hits: list[SearchHit],
    vec_hits: list[SearchHit],
    *,
    limit: int,
    rrf_k: int = _RRF_K,
) -> list[SearchHit]:
    """RRF 融合。

    FTS 文件级 hit（无 chunk）以 ulid 去重 + 累加；
    vec hit 以 (ulid, chunk_id) 去重 + 累加。
    同一 hit 在 FTS / vec 都出现 → 合并到 chunk 粒度的同一条（若 vec 有 chunk）。
    """
    # (key -> (SearchHit, rrf_score, has_chunk))
    acc: dict[tuple, tuple[SearchHit, float, bool]] = {}

    def add(hit: SearchHit, rank: int, has_chunk: bool) -> None:
        if has_chunk:
            key = ("c", hit.ulid, hit.chunk.chunk_id)  # type: ignore[union-attr]
        else:
            key = ("d", hit.ulid, None)
        rrf = 1.0 / (rrf_k + rank + 1)
        if key in acc:
            old_hit, old_score, old_chunk = acc[key]
            # 若新 hit 有 chunk 但旧的没有，用新的覆盖（保留 chunk 引用）
            if has_chunk and not old_chunk:
                acc[key] = (hit, old_score + rrf, True)
            else:
                acc[key] = (old_hit, old_score + rrf, old_chunk or has_chunk)
        else:
            acc[key] = (hit, rrf, has_chunk)

    for i, h in enumerate(fts_hits):
        add(h, i, h.chunk is not None)
    for i, h in enumerate(vec_hits):
        add(h, i, h.chunk is not None)

    ranked = sorted(acc.values(), key=lambda x: x[1], reverse=True)[:limit]
    out: list[SearchHit] = []
    for hit, score, has_chunk in ranked:
        hit.score = float(score)
        out.append(hit)
    return out


# ── 旧接口保留（chunk 级别 FTS，预留） ─────────────────────────────


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
