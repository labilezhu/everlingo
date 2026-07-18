# ref: docs/impl-spec/search/memory-vault-embedding-spec.md — Embedding store
# 覆盖 pack/upsert/knn/prune/rebuild_for_model；用 fake embedder 产出确定性向量。
# 加载 sqlite-vec 扩展：测试在 :memory: 上自行 conn.enable_load_extension 后跑。

from __future__ import annotations

import sqlite3
import struct
from pathlib import Path

import pytest
import sqlite_vec

from everlingo.mem.vault.search import indexer
from everlingo.mem.vault.search.embedding import store
from everlingo.mem.vault.search.indexer import init_db


# ── helpers ─────────────────────────────────────────────────────────


DIM = 4


class FakeEmbedder:
    """按文本 hash 生成确定性向量的 fake embedder。"""

    def __init__(self, dim: int = DIM) -> None:
        self.dim = dim
        self.calls: list[list[str]] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [_fake_vec(t, self.dim) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return _fake_vec(text, self.dim)


def _fake_vec(text: str, dim: int) -> list[float]:
    """把 text hash 成 dim 维 unit vector（粗略但稳定）。"""
    import hashlib

    h = hashlib.sha256(text.encode("utf-8")).digest()
    raw = [b / 255.0 - 0.5 for b in h[:dim]]
    # 单位化
    norm = sum(x * x for x in raw) ** 0.5 or 1.0
    return [x / norm for x in raw]


def _load_vec0(conn: sqlite3.Connection) -> None:
    conn.enable_load_extension(True)
    conn.load_extension(sqlite_vec.loadable_path())
    conn.enable_load_extension(False)


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "memory.sqlite"
    c = sqlite3.connect(str(db_path))
    c.execute("PRAGMA foreign_keys=ON")
    _load_vec0(c)
    init_db(c)
    yield c
    c.close()


def _set_model(conn: sqlite3.Connection, model_id: str = "m", dim: int = DIM) -> None:
    """set_current_model 包装，避免每个测试都写。"""
    store.set_current_model(conn, model_id, dim)


def _insert_one_doc(
    conn: sqlite3.Connection,
    ulid: str = "01JZBSTORE1",
    text: str = "hello world",
    *,
    item_type: str = "vocab",
) -> int:
    """直接写一个 doc + 一个 chunk，返回 chunk_id。"""
    cur = conn.execute(
        """
        INSERT INTO documents(
            ulid, kind, item_type, file_path, slug, headword, title,
            body, content_hash, file_mtime, indexed_at
        ) VALUES (?, 'item', ?, ?, ?, ?, ?, ?, 'h1', '2026-01-01', '2026-01-01')
        """,
        (ulid, item_type, f"items/vocab/{ulid}.md", "x", "x", "x", text),
    )
    rowid = cur.lastrowid
    cur = conn.execute(
        """
        INSERT INTO chunks(doc_rowid, chunk_index, text, content_hash)
        VALUES (?, 0, ?, 'h1')
        """,
        (rowid, text),
    )
    return cur.lastrowid


# ── pack / unpack ────────────────────────────────────────────────


def test_pack_unpack_roundtrip():
    v = [0.1, 0.2, 0.3, 0.4]
    blob = store.pack_vector(v, 4)
    assert len(blob) == 16
    assert store.unpack_vector(blob, 4) == pytest.approx(v)


def test_pack_wrong_dim_raises():
    with pytest.raises(ValueError):
        store.pack_vector([0.1, 0.2], 4)


# ── ensure_vec_table ─────────────────────────────────────────────


def test_ensure_vec_table_idempotent(conn: sqlite3.Connection):
    store.ensure_vec_table(conn, DIM)
    assert store.has_vec_table(conn)
    # 重复建不报错
    store.ensure_vec_table(conn, DIM)
    assert store.has_vec_table(conn)


def test_vec0_available_smoke(conn: sqlite3.Connection):
    assert store.vec0_available(conn) is True


# ── batch_upsert / pending ───────────────────────────────────────


def test_pending_chunk_ids_empty(conn: sqlite3.Connection):
    assert store.pending_chunk_ids(conn, model_id="m", limit=10) == []


def test_batch_upsert_writes_embeddings_and_vec(conn: sqlite3.Connection):
    store.ensure_vec_table(conn, DIM)
    cid1 = _insert_one_doc(conn, ulid="01JZBST001", text="apple")
    cid2 = _insert_one_doc(conn, ulid="01JZBST002", text="banana")
    emb = FakeEmbedder()
    n = store.batch_upsert(
        conn,
        [(cid1, "apple"), (cid2, "banana")],
        emb,
        model_id="m1",
        dim=DIM,
    )
    assert n == 2
    # chunk_embeddings 行
    rows = conn.execute(
        "SELECT chunk_id, model_id, dim, length(embedding) FROM chunk_embeddings ORDER BY chunk_id"
    ).fetchall()
    assert [r[0] for r in rows] == [cid1, cid2]
    assert all(r[1] == "m1" and r[2] == DIM and r[3] == 16 for r in rows)
    # vec0 行
    vec_rows = conn.execute(
        "SELECT chunk_id FROM chunk_vec ORDER BY chunk_id"
    ).fetchall()
    assert [r[0] for r in vec_rows] == [cid1, cid2]
    # pending 列表已空
    assert store.pending_chunk_ids(conn, model_id="m1", limit=10) == []


def test_pending_chunk_ids_filter_by_model(conn: sqlite3.Connection):
    """旧 model_id 的 embedding 不应让新 model_id 跳过。"""
    store.ensure_vec_table(conn, DIM)
    _set_model(conn, model_id="m-old")
    emb = FakeEmbedder()
    cid = _insert_one_doc(conn, ulid="01JZBST003", text="cherry")
    store.batch_upsert(conn, [(cid, "cherry")], emb, model_id="m-old", dim=DIM)
    # 换模型后应被 pending
    assert store.pending_chunk_ids(conn, model_id="m-new", limit=10) == [(cid, "cherry")]


def test_batch_upsert_embedder_mismatch_raises(conn: sqlite3.Connection):
    store.ensure_vec_table(conn, DIM)
    cid = _insert_one_doc(conn, ulid="01JZBST004", text="x")

    class BadEmbedder:
        def embed_documents(self, texts):
            return [[0.0] * DIM]  # 长度 = 1 != len(items) = 1 也要抛
        def embed_query(self, text):
            return [0.0] * DIM

    with pytest.raises(RuntimeError, match="不一致"):
        store.batch_upsert(
            conn, [(cid, "x"), (cid, "y")], BadEmbedder(), model_id="m", dim=DIM
        )


# ── knn ──────────────────────────────────────────────────────────


def test_knn_returns_closest_first(conn: sqlite3.Connection):
    store.ensure_vec_table(conn, DIM)
    _set_model(conn)
    emb = FakeEmbedder()
    # 同样的 text → 同样 vec；不同 text 距离都非零
    texts = ["alpha", "beta", "gamma", "delta"]
    cids: list[int] = []
    for i, t in enumerate(texts):
        cids.append(
            _insert_one_doc(conn, ulid=f"01JZBKN00{i}", text=t)
        )
    store.batch_upsert(conn, list(zip(cids, texts)), emb, model_id="m", dim=DIM)
    conn.commit()
    # 查询 "alpha" → 距离最小的是 alpha 自己（distance=0）
    knn = store.knn_with_filter(conn, emb.embed_query("alpha"), k=4)
    assert knn[0][0] == cids[0]
    assert knn[0][1] == 0.0  # cosine distance 0 = 完全相同
    # 其余 3 个距离 > 0
    assert all(d > 0 for _, d in knn[1:])


def test_knn_with_filter_item_type(conn: sqlite3.Connection):
    """per-lang DB 内按 item_type 过滤（lang 过滤已隐含）。"""
    store.ensure_vec_table(conn, DIM)
    _set_model(conn)
    emb = FakeEmbedder()
    c1 = _insert_one_doc(conn, ulid="01JZBF001", text="hello", item_type="vocab")
    c2 = _insert_one_doc(conn, ulid="01JZBF002", text="hello-grammar", item_type="grammar")
    store.batch_upsert(
        conn, [(c1, "hello"), (c2, "hello-grammar")],
        emb, model_id="m", dim=DIM,
    )
    conn.commit()
    # item_type=vocab
    knn = store.knn_with_filter(
        conn, emb.embed_query("hello"), k=10, item_type="vocab"
    )
    chunk_ids = [c for c, _ in knn]
    assert chunk_ids == [c1]
    # item_type=grammar
    knn2 = store.knn_with_filter(
        conn, emb.embed_query("hello"), k=10, item_type="grammar"
    )
    assert [c for c, _ in knn2] == [c2]


def test_knn_no_vec_table_returns_empty(conn: sqlite3.Connection):
    """未建 vec0 时 KNN 不可用，返回空。"""
    knn = store.knn_with_filter(conn, [0.0] * DIM, k=4)
    assert knn == []


# ── prune_orphan_vec_rows ───────────────────────────────────────


def test_prune_removes_orphan_vec_rows(conn: sqlite3.Connection):
    """chunk_embeddings 删了（如 chunks CASCADE）vec0 不会自动清；prune 补上。"""
    store.ensure_vec_table(conn, DIM)
    _set_model(conn)
    emb = FakeEmbedder()
    cid = _insert_one_doc(conn, ulid="01JZBPR001", text="orphan")
    store.batch_upsert(conn, [(cid, "orphan")], emb, model_id="m", dim=DIM)
    # 模拟 chunks CASCADE：直接删 documents（chunks / chunk_embeddings 级联删）
    conn.execute("DELETE FROM documents WHERE rowid = (SELECT doc_rowid FROM chunks WHERE chunk_id=?)", (cid,))
    conn.commit()
    # chunk_embeddings 已无 cid，vec0 仍有
    n = conn.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0]
    assert n == 0
    m = conn.execute("SELECT COUNT(*) FROM chunk_vec").fetchone()[0]
    assert m == 1
    # prune 清掉孤儿
    pruned = store.prune_orphan_vec_rows(conn)
    assert pruned == 1
    assert conn.execute("SELECT COUNT(*) FROM chunk_vec").fetchone()[0] == 0


# ── sync_vec_table_from_embeddings ─────────────────────────────


def test_sync_vec_table_rebuilds_from_embeddings(conn: sqlite3.Connection):
    store.ensure_vec_table(conn, DIM)
    _set_model(conn)
    emb = FakeEmbedder()
    c1 = _insert_one_doc(conn, ulid="01JZBSY001", text="one")
    c2 = _insert_one_doc(conn, ulid="01JZBSY002", text="two")
    store.batch_upsert(conn, [(c1, "one"), (c2, "two")], emb, model_id="m", dim=DIM)
    # 模拟 vec0 损坏（手动清空）
    conn.execute(f"DELETE FROM {store.VEC_TABLE}")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM chunk_vec").fetchone()[0] == 0
    # sync 恢复
    n = store.sync_vec_table_from_embeddings(conn, model_id="m", dim=DIM)
    assert n == 2
    assert conn.execute("SELECT COUNT(*) FROM chunk_vec").fetchone()[0] == 2


# ── rebuild_for_model ───────────────────────────────────────────


def test_rebuild_for_model_drops_and_re_embeds(conn: sqlite3.Connection):
    # 先按 m1 嵌入
    store.ensure_vec_table(conn, DIM)
    emb = FakeEmbedder()
    cids = [
        _insert_one_doc(conn, ulid=f"01JZRBM00{i}", text=f"t{i}")
        for i in range(3)
    ]
    _set_model(conn, model_id="m1", dim=DIM)
    store.batch_upsert(conn, list(zip(cids, [f"t{i}" for i in range(3)])),
                       emb, model_id="m1", dim=DIM)
    assert store.current_model_id(conn) == "m1"
    # rebuild 成 m2
    n = store.rebuild_for_model(conn, "m2", DIM, emb, batch=2)
    assert n == 3
    assert store.current_model_id(conn) == "m2"
    assert store.current_dim(conn) == DIM
    rows = conn.execute(
        f"SELECT COUNT(*) FROM chunk_embeddings WHERE model_id='m2'"
    ).fetchone()[0]
    assert rows == 3
    # 旧 m1 的行已被清
    old = conn.execute(
        f"SELECT COUNT(*) FROM chunk_embeddings WHERE model_id='m1'"
    ).fetchone()[0]
    assert old == 0
    assert conn.execute("SELECT COUNT(*) FROM chunk_vec").fetchone()[0] == 3
