# ref: docs/impl-spec/search/memory-vault-embedding-spec.md — Embedding worker
# indexer 进程内后台守护线程，异步补嵌 chunks。
# 触发：reconcile 后启动 / index_file 后 wake / rebuild 后全量重嵌。
# 降级：embedder 不可用时不启动；查询侧回退 FTS。

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from typing import Callable

from . import store

logger = logging.getLogger(__name__)


class EmbeddingWorker:
    """后台补嵌线程。

    使用方式：
        worker = EmbeddingWorker(conn, embedder, model_id, dim, ...)
        worker.start()
        # ... index_file 时调 worker.wake()
        worker.stop()
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        embedder: store.Embedder,
        *,
        model_id: str,
        dim: int,
        interval: float = 2.0,
        batch: int = 64,
        max_retries: int = 3,
        backoff_base: float = 1.5,
    ) -> None:
        self._conn = conn
        self._embedder = embedder
        self._model_id = model_id
        self._dim = dim
        self._interval = interval
        self._batch = batch
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dim(self) -> int:
        return self._dim

    def start(self) -> None:
        if self._thread is not None:
            return
        # 启动前同步 vec0（防御 vec0 表丢失）
        try:
            store.sync_vec_table_from_embeddings(
                self._conn, model_id=self._model_id, dim=self._dim
            )
        except Exception as e:
            logger.warning("sync_vec_table_from_embeddings 失败: %s", e)
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="EmbeddingWorker", daemon=True
        )
        self._thread.start()
        logger.info(
            "EmbeddingWorker 启动: model_id=%s dim=%d batch=%d",
            self._model_id,
            self._dim,
            self._batch,
        )

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
            logger.info("EmbeddingWorker 停止")

    def wake(self) -> None:
        self._wake.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._drain_once()
            # 等待：wake 或 interval 秒到
            self._wake.wait(timeout=self._interval)
            self._wake.clear()

    def _drain_once(self) -> None:
        """处理一批 pending；遇错误按退避重试，单批失败不阻塞下批。"""
        retries = 0
        while not self._stop.is_set():
            try:
                pending = store.pending_chunk_ids(
                    self._conn, model_id=self._model_id, limit=self._batch
                )
            except Exception as e:
                logger.warning("查询 pending 失败: %s", e)
                return
            if not pending:
                return
            try:
                store.batch_upsert(
                    self._conn,
                    pending,
                    self._embedder,
                    model_id=self._model_id,
                    dim=self._dim,
                )
                # 清 vec0 孤儿（chunks CASCADE 删除时联动）
                try:
                    store.prune_orphan_vec_rows(self._conn)
                except Exception as e:
                    logger.debug("prune_orphan_vec_rows 失败（可忽略）: %s", e)
                self._conn.commit()
                logger.debug("补嵌 batch=%d", len(pending))
                retries = 0
            except Exception as e:
                retries += 1
                wait = self._backoff_base**retries
                logger.warning(
                    "embed 失败 (第 %d 次)，%ds 后重试: %s", retries, wait, e
                )
                if retries >= self._max_retries:
                    logger.error(
                        "embed 失败已达 %d 次，本批留待下轮: %s",
                        self._max_retries,
                        e,
                    )
                    return
                self._stop.wait(timeout=wait)
