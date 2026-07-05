# ref: docs/impl-spec/search/memory-vault-embedding-spec.md — Embedding store
# 向量存取层：管理 chunk_embeddings（权威存储）+ chunk_vec（vec0 KNN 索引）。
# gateway 进程不加载本模块；indexer 进程内串行调用。

from __future__ import annotations

import logging
import sqlite3
import struct
import time
from typing import Iterable, Protocol

from ..indexer import get_meta, set_meta

logger = logging.getLogger(__name__)


# ── 抽象：embedder 协议 ─────────────────────────────────────────────


class Embedder(Protocol):
    """worker / store 期望的 embedder 协议（duck-type 兼容 AIEmbedding）。"""

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


# ── 序列化 / 反序列化 ────────────────────────────────────────────────


def pack_vector(vec: list[float], dim: int) -> bytes:
    """float32 little-endian packed bytes。"""
    if len(vec) != dim:
        raise ValueError(f"vector dim mismatch: got {len(vec)}, expected {dim}")
    return struct.pack(f"<{dim}f", *vec)


def unpack_vector(blob: bytes, dim: int) -> list[float]:
    return list(struct.unpack(f"<{dim}f", blob))


# ── 模型配置 ─────────────────────────────────────────────────────────


def current_model_id(conn: sqlite3.Connection) -> str | None:
    return get_meta(conn, "embedding_model_id")


def current_dim(conn: sqlite3.Connection) -> int | None:
    v = get_meta(conn, "embedding_dim")
    return int(v) if v else None


def set_current_model(conn: sqlite3.Connection, model_id: str, dim: int) -> None:
    set_meta(conn, "embedding_model_id", model_id)
    set_meta(conn, "embedding_dim", str(dim))
    set_meta(conn, "embedding_schema_version", "1")


# ── vec0 虚表管理 ───────────────────────────────────────────────────


VEC_TABLE = "chunk_vec"
EMB_TABLE = "chunk_embeddings"


def _vec_table_ddl(dim: int) -> str:
    return (
        f"CREATE VIRTUAL TABLE IF NOT EXISTS {VEC_TABLE} USING vec0("
        f"chunk_id INTEGER PRIMARY KEY, "
        f"embedding FLOAT[{dim}] distance_metric=cosine)"
    )


def has_vec_table(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (VEC_TABLE,)
    ).fetchone()
    return row is not None


def vec0_available(conn: sqlite3.Connection) -> bool:
    """检测 vec0 扩展是否生效。"""
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (VEC_TABLE,)
        ).fetchone()
        if row is not None:
            return True
        # 尝试建个 0 维临时虚表验证扩展可用
        conn.execute("CREATE VIRTUAL TABLE _vec_probe USING vec0(e FLOAT[2])")
        conn.execute("DROP TABLE _vec_probe")
        return True
    except Exception:
        return False


def ensure_vec_table(conn: sqlite3.Connection, dim: int) -> None:
    """建 chunk_vec 虚表（幂等）。dim 必须与 current_dim 一致。"""
    conn.execute(_vec_table_ddl(dim))
    logger.info("vec0 虚表就绪: %s dim=%d", VEC_TABLE, dim)


def drop_vec_table(conn: sqlite3.Connection) -> None:
    conn.execute(f"DROP TABLE IF EXISTS {VEC_TABLE}")


# ── 单条 / 批量写 ────────────────────────────────────────────────────


def upsert_embedding(
    conn: sqlite3.Connection,
    chunk_id: int,
    text: str,
    embedder: Embedder,
    *,
    model_id: str,
    dim: int,
) -> None:
    """算单个 chunk 向量并写库（chunk_embeddings + chunk_vec）。"""
    vec = embedder.embed_documents([text])[0]
    blob = pack_vector(vec, dim)
    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    conn.execute(
        f"""
        INSERT INTO {EMB_TABLE}(chunk_id, model_id, dim, embedding, embedded_at)
        VALUES(?, ?, ?, ?, ?)
        ON CONFLICT(chunk_id) DO UPDATE SET
            model_id=excluded.model_id,
            dim=excluded.dim,
            embedding=excluded.embedding,
            embedded_at=excluded.embedded_at
        """,
        (chunk_id, model_id, dim, blob, now),
    )
    conn.execute(
        f"INSERT OR REPLACE INTO {VEC_TABLE}(chunk_id, embedding) VALUES(?, ?)",
        (chunk_id, blob),
    )


def batch_upsert(
    conn: sqlite3.Connection,
    items: list[tuple[int, str]],
    embedder: Embedder,
    *,
    model_id: str,
    dim: int,
) -> int:
    """批量嵌入并写库；返回成功写入数（整批任一失败则整批回滚，外部负责重试）。"""
    if not items:
        return 0
    texts = [t for _, t in items]
    vecs = embedder.embed_documents(texts)
    if len(vecs) != len(items):
        raise RuntimeError(
            f"embedder 返回向量数 ({len(vecs)}) 与输入数 ({len(items)}) 不一致"
        )
    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    for (chunk_id, _), vec in zip(items, vecs):
        blob = pack_vector(vec, dim)
        conn.execute(
            f"""
            INSERT INTO {EMB_TABLE}(chunk_id, model_id, dim, embedding, embedded_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(chunk_id) DO UPDATE SET
                model_id=excluded.model_id,
                dim=excluded.dim,
                embedding=excluded.embedding,
                embedded_at=excluded.embedded_at
            """,
            (chunk_id, model_id, dim, blob, now),
        )
        conn.execute(
            f"INSERT OR REPLACE INTO {VEC_TABLE}(chunk_id, embedding) VALUES(?, ?)",
            (chunk_id, blob),
        )
    return len(items)


# ── pending 选择 ────────────────────────────────────────────────────


def pending_chunk_ids(
    conn: sqlite3.Connection, *, model_id: str, limit: int
) -> list[tuple[int, str]]:
    """返回当前模型下未嵌入（或旧 model_id）的 (chunk_id, text) 列表。

    chunks 被 documents DELETE 时级联清理（CASCADE），所以 pending 自动
    包含因文件被删/改而需重新嵌入的 chunk。
    """
    rows = conn.execute(
        f"""
        SELECT c.chunk_id, c.text FROM chunks c
        LEFT JOIN {EMB_TABLE} e ON e.chunk_id = c.chunk_id AND e.model_id = ?
        WHERE e.chunk_id IS NULL
        LIMIT ?
        """,
        (model_id, limit),
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


# ── 统计 ────────────────────────────────────────────────────────────


def count_embedded(conn: sqlite3.Connection, *, model_id: str) -> int:
    return conn.execute(
        f"SELECT COUNT(*) FROM {EMB_TABLE} WHERE model_id=?", (model_id,)
    ).fetchone()[0]


def count_chunks(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]


# ── KNN 查询 ────────────────────────────────────────────────────────


def _vec0_knn(
    conn: sqlite3.Connection,
    query_vec: list[float],
    k: int,
) -> list[tuple[int, float]]:
    """vec0 KNN：返回 (chunk_id, distance) 升序。"""
    dim = current_dim(conn)
    if dim is None or not has_vec_table(conn):
        return []
    blob = pack_vector(query_vec, dim)
    rows = conn.execute(
        f"SELECT chunk_id, distance FROM {VEC_TABLE} "
        f"WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
        (blob, k),
    ).fetchall()
    return [(int(r[0]), float(r[1])) for r in rows]


def knn_with_filter(
    conn: sqlite3.Connection,
    query_vec: list[float],
    *,
    k: int,
    item_type: str | None = None,
    kind: str | None = None,
    tags: list[str] | None = None,
) -> list[tuple[int, float]]:
    """带过滤的 KNN：先取 k*3 候选，再 join chunks/documents 过滤。

    距离按 sqlite-vec cosine distance（0=同向，2=反向）。
    lang 过滤已隐含于 per-lang DB，不再需要。
    """
    overfetch = max(k * 3, k)
    candidates = _vec0_knn(conn, query_vec, overfetch)
    if not candidates:
        return []

    chunk_ids = [cid for cid, _ in candidates]
    placeholders = ",".join("?" * len(chunk_ids))
    params: list = list(chunk_ids)
    clauses = [f"c.chunk_id IN ({placeholders})"]
    if item_type is not None:
        clauses.append("d.item_type = ?")
        params.append(item_type)
    if kind is not None:
        clauses.append("d.kind = ?")
        params.append(kind)
    if tags:
        # tags 存 ' ' 连接，做包含判定（与 FTS 路径一致）
        for t in tags:
            clauses.append("d.tags LIKE ?")
            params.append(f"%{t}%")

    rows = conn.execute(
        f"""
        SELECT c.chunk_id FROM chunks c
        JOIN documents d ON d.rowid = c.doc_rowid
        WHERE {' AND '.join(clauses)}
        """,
        params,
    ).fetchall()
    allowed = {r[0] for r in rows}

    # 保持原 vec0 距离顺序
    out = [(cid, dist) for cid, dist in candidates if cid in allowed]
    return out[:k]


# ── 模型作废 + 重建 ─────────────────────────────────────────────────


def rebuild_for_model(
    conn: sqlite3.Connection,
    new_model_id: str,
    new_dim: int,
    embedder: Embedder,
    *,
    batch: int = 64,
) -> int:
    """drop 旧 chunk_vec + 清 chunk_embeddings；建新 vec0；批量重嵌全量。

    返回成功嵌入的 chunk 数。
    """
    set_current_model(conn, new_model_id, new_dim)
    conn.execute(f"DELETE FROM {EMB_TABLE}")
    drop_vec_table(conn)
    ensure_vec_table(conn, new_dim)

    total = 0
    while True:
        pending = pending_chunk_ids(conn, model_id=new_model_id, limit=batch)
        if not pending:
            break
        n = batch_upsert(conn, pending, embedder, model_id=new_model_id, dim=new_dim)
        total += n
        conn.commit()
    logger.info(
        "rebuild_for_model: model_id=%s dim=%d total=%d",
        new_model_id,
        new_dim,
        total,
    )
    return total


# ── 启动期同步：chunk_vec ↔ chunk_embeddings ──────────────────────


def sync_vec_table_from_embeddings(
    conn: sqlite3.Connection, *, model_id: str, dim: int
) -> int:
    """indexer 启动时把 chunk_embeddings 同步进 chunk_vec（vec0 不持久化或
    索引损坏时也能恢复）。返回同步行数。

    同时清理 chunk_vec 中 chunk_id 已不存在于 chunks 表的孤儿行。
    """
    if not has_vec_table(conn):
        ensure_vec_table(conn, dim)
    # 清空 vec0
    conn.execute(f"DELETE FROM {VEC_TABLE}")
    # 同步 chunk_embeddings → chunk_vec
    rows = conn.execute(
        f"SELECT chunk_id, embedding FROM {EMB_TABLE} WHERE model_id=?",
        (model_id,),
    ).fetchall()
    for chunk_id, blob in rows:
        conn.execute(
            f"INSERT OR REPLACE INTO {VEC_TABLE}(chunk_id, embedding) VALUES(?, ?)",
            (chunk_id, blob),
        )
    logger.info("sync_vec_table_from_embeddings: synced %d rows", len(rows))
    return len(rows)


def prune_orphan_vec_rows(conn: sqlite3.Connection) -> int:
    """清理 chunk_vec 中已无对应 chunk（或 chunk_embeddings 行）的行。

    触发时机：worker 每批嵌入后 / 启动期 sync_vec_table_from_embeddings 后。
    必要性：chunks CASCADE → chunk_embeddings 时 vec0 无 FK 联动。
    """
    if not has_vec_table(conn):
        return 0
    # chunk_vec 行 - chunk_embeddings 行 = 孤儿
    cur = conn.execute(
        f"""
        DELETE FROM {VEC_TABLE}
        WHERE chunk_id NOT IN (
            SELECT e.chunk_id FROM {EMB_TABLE} e WHERE e.model_id = (
                SELECT value FROM meta WHERE key='embedding_model_id'
            )
        )
        """
    )
    return cur.rowcount
