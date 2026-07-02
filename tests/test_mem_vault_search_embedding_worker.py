# ref: docs/impl-spec/search/memory-vault-embedding-spec.md — Embedding worker
# 测：pending 选择 / 批量 / wake / 失败重试 / start-stop / 内容未变短路。

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest
import sqlite_vec

from everlingo.mem.vault.search import indexer
from everlingo.mem.vault.search.embedding import store
from everlingo.mem.vault.search.embedding.worker import EmbeddingWorker
from everlingo.mem.vault.search.indexer import init_db


DIM = 4


class FakeEmbedder:
    """确定性 hash 向量；可注入错误模拟 API 失败。"""

    def __init__(self, dim: int = DIM, fail_n: int = 0) -> None:
        self.dim = dim
        self.calls: list[list[str]] = []
        self.fail_n = fail_n
        self.errors_remaining = fail_n

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self.errors_remaining > 0:
            self.errors_remaining -= 1
            raise RuntimeError(f"fake API error (remaining={self.errors_remaining})")
        return [_fake_vec(t, self.dim) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return _fake_vec(text, self.dim)


def _fake_vec(text: str, dim: int) -> list[float]:
    import hashlib

    h = hashlib.sha256(text.encode("utf-8")).digest()
    raw = [b / 255.0 - 0.5 for b in h[:dim]]
    norm = sum(x * x for x in raw) ** 0.5 or 1.0
    return [x / norm for x in raw]


def _load_vec0(conn: sqlite3.Connection) -> None:
    conn.enable_load_extension(True)
    conn.load_extension(sqlite_vec.loadable_path())
    conn.enable_load_extension(False)


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "memory.sqlite"
    c = sqlite3.connect(str(db_path), check_same_thread=False)
    c.execute("PRAGMA foreign_keys=ON")
    _load_vec0(c)
    init_db(c)
    store.set_current_model(c, "m", DIM)
    store.ensure_vec_table(c, DIM)
    yield c
    c.close()


def _insert_one(conn: sqlite3.Connection, ulid: str, text: str) -> int:
    cur = conn.execute(
        """
        INSERT INTO documents(ulid, kind, file_path, body, content_hash,
                              file_mtime, indexed_at)
        VALUES (?, 'item', ?, 'b', 'h', 'm', 'i')
        """,
        (ulid, f"p/{ulid}"),
    )
    rowid = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO chunks(doc_rowid, chunk_index, text, content_hash) "
        "VALUES (?, 0, ?, 'h')",
        (rowid, text),
    )
    return cur.lastrowid


# ── pending → batch → commit ──────────────────────────────────────


def test_worker_pending_empty_drains_nothing(conn: sqlite3.Connection):
    emb = FakeEmbedder()
    w = EmbeddingWorker(conn, emb, model_id="m", dim=DIM, interval=0.1)
    w.start()
    try:
        # 等待几次 tick
        time.sleep(0.3)
    finally:
        w.stop()
    # 没 pending 时不应调 embedder
    assert emb.calls == []


def test_worker_embeds_pending_chunks(conn: sqlite3.Connection):
    emb = FakeEmbedder()
    cids = [
        _insert_one(conn, f"01JZWK00{i}", f"text-{i}") for i in range(5)
    ]
    w = EmbeddingWorker(conn, emb, model_id="m", dim=DIM,
                        interval=0.05, batch=2)
    w.start()
    try:
        # 等所有 5 个 chunk 嵌入完成（>0.5s 给 3 批 + 退避余量）
        deadline = time.time() + 3.0
        while time.time() < deadline:
            n = conn.execute(
                "SELECT COUNT(*) FROM chunk_embeddings"
            ).fetchone()[0]
            if n == 5:
                break
            time.sleep(0.1)
        w.wake()  # 唤醒一次以加快
    finally:
        w.stop()
    n = conn.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0]
    assert n == 5
    m = conn.execute("SELECT COUNT(*) FROM chunk_vec").fetchone()[0]
    assert m == 5
    # embedder 至少被调 3 次（5 个 / batch 2 = ceil 3）
    assert len(emb.calls) >= 3
    # 所有调用都走 batch_upsert（去重后应是 2/2/1 之类）
    assert sum(len(c) for c in emb.calls) == 5


def test_worker_wake_triggers_immediate_drain(conn: sqlite3.Connection):
    emb = FakeEmbedder()
    w = EmbeddingWorker(conn, emb, model_id="m", dim=DIM, interval=10.0)
    w.start()
    try:
        # 此时无 pending
        time.sleep(0.1)
        cids = [_insert_one(conn, f"01JZWK01{i}", f"t{i}") for i in range(2)]
        # interval=10s 不会自然触发；显式 wake
        w.wake()
        deadline = time.time() + 2.0
        while time.time() < deadline:
            n = conn.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0]
            if n == 2:
                break
            time.sleep(0.05)
    finally:
        w.stop()
    assert conn.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0] == 2


def test_worker_retries_on_failure(conn: sqlite3.Connection):
    """前 2 次 embed_documents 失败 → 第 3 次成功。"""
    emb = FakeEmbedder(fail_n=2)
    w = EmbeddingWorker(
        conn, emb, model_id="m", dim=DIM,
        interval=0.05, batch=4,
        max_retries=5, backoff_base=1.2,  # 退避短
    )
    cid = _insert_one(conn, "01JZWKRETRY", "retry-me")
    w.start()
    try:
        deadline = time.time() + 5.0
        while time.time() < deadline:
            n = conn.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0]
            if n == 1:
                break
            time.sleep(0.1)
    finally:
        w.stop()
    assert n == 1
    # 至少调了 3 次（前 2 次失败 + 1 次成功）
    assert len(emb.calls) >= 3


def test_worker_max_retries_aborts_batch(conn: sqlite3.Connection):
    """持续失败 → max_retries 后停批，下轮再试。"""
    emb = FakeEmbedder(fail_n=100)
    w = EmbeddingWorker(
        conn, emb, model_id="m", dim=DIM,
        interval=0.05, batch=2,
        max_retries=2, backoff_base=1.1,
    )
    _insert_one(conn, "01JZWKABORT", "x")
    w.start()
    try:
        # 等到 worker 已经至少试过 max_retries 次（不要求时间精确）
        time.sleep(1.5)
    finally:
        w.stop()
    # 仍有未嵌入 chunk（max_retries 后留待下轮）
    assert conn.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0] == 0
    # 调用次数 ≥ max_retries（2）
    assert len(emb.calls) >= 2


def test_worker_sync_vec_table_on_start(conn: sqlite3.Connection):
    """启动时把 chunk_embeddings 同步进 vec0（防 vec0 损坏）。"""
    # 先正常嵌入
    emb = FakeEmbedder()
    cid = _insert_one(conn, "01JZWKSYNC", "sync-text")
    store.batch_upsert(conn, [(cid, "sync-text")], emb, model_id="m", dim=DIM)
    conn.commit()
    # 模拟 vec0 损坏
    conn.execute("DELETE FROM chunk_vec")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM chunk_vec").fetchone()[0] == 0
    # 启 worker
    w = EmbeddingWorker(conn, emb, model_id="m", dim=DIM, interval=10.0)
    w.start()
    try:
        time.sleep(0.2)
    finally:
        w.stop()
    # vec0 已恢复
    assert conn.execute("SELECT COUNT(*) FROM chunk_vec").fetchone()[0] == 1
