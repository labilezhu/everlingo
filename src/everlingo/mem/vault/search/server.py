# ref: docs/impl-spec/search/memory-vault-search-spec.md — IPC 协议 / server.py
# FastAPI app + uvicorn --uds $workspace/memory/vault_index/indexer.sock 入口。
# 5 个端点：POST /search, POST /index, POST /delete, POST /rebuild, GET /status
# indexer 进程内 import；gateway 进程不加载本文件。

from __future__ import annotations

import logging
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException

from . import search
from .embedding import store
from .embedding.ai_embedding import AIEmbedding
from .embedding.worker import EmbeddingWorker
from .indexer import (
    count_chunks,
    count_docs,
    delete_file,
    index_file,
    parse_file,
    set_meta,
)
from .protocol import (
    EmbedRequest,
    EmbedResponse,
    IndexRequest,
    OkResponse,
    RebuildResponse,
    SearchRequest,
    SearchResponse,
    StatusResponse,
)
from .sync import open_db, reconcile
from .tokenizer import tokenizer_version
from .watcher import VaultWatcher

logger = logging.getLogger(__name__)


# ── 应用状态 ─────────────────────────────────────────────────────────


class AppState:
    """indexer 进程内的全局状态（FastAPI lifespan 注入）。"""

    def __init__(
        self,
        db_path: Path,
        memory_root: Path,
        socket_path: Path,
    ) -> None:
        self.db_path = db_path
        self.memory_root = memory_root
        self.socket_path = socket_path
        self.started_at = time.time()
        self.conn: sqlite3.Connection | None = None
        self.watcher: VaultWatcher | None = None
        self.embedder = None
        self.worker: EmbeddingWorker | None = None

    def _init_embedder(self) -> None:
        """尝试构造 embedder。失败（模型未配）则保持 None，FTS 不受影响。"""
        try:
            self.embedder = AIEmbedding.create()
        except ValueError as e:
            logger.info("embedder 未启用: %s（semantic/hybrid 模式将降级）", e)
            self.embedder = None
        except Exception as e:
            logger.warning("构造 embedder 失败: %s", e)
            self.embedder = None

    def _start_worker(self) -> None:
        if self.embedder is None or self.conn is None:
            return
        model_id = store.current_model_id(self.conn)
        dim = store.current_dim(self.conn)
        if model_id is None or dim is None:
            # 首次启动：探测 embedder 维度
            try:
                probe = self.embedder.embed_query("dimension probe")
                dim = len(probe)
            except Exception as e:
                logger.warning("探测 embedding 维度失败: %s", e)
                return
            model_id = self.embedder.model
            store.set_current_model(self.conn, model_id, dim)
        # vec0 扩展未生效 → 不起 worker
        if not store.vec0_available(self.conn):
            logger.info("vec0 不可用，embedding worker 不启动")
            return
        if not store.has_vec_table(self.conn):
            store.ensure_vec_table(self.conn, dim)
        self.worker = EmbeddingWorker(
            self.conn, self.embedder, model_id=model_id, dim=dim
        )
        self.worker.start()

    def _stop_worker(self) -> None:
        if self.worker is not None:
            self.worker.stop()
            self.worker = None

    def open(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.memory_root.mkdir(parents=True, exist_ok=True)
        self.conn = open_db(self.db_path)
        # 启动对账
        result = reconcile(self.conn, self.memory_root)
        # 启动 watcher
        self.watcher = VaultWatcher(self.conn, self.memory_root)
        self.watcher.start()
        # 启动 embedding worker
        self._init_embedder()
        self._start_worker()
        logger.info(
            "indexer ready: db=%s sock=%s reconcile indexed=%d skipped=%d orphans=%d",
            self.db_path,
            self.socket_path,
            result.indexed,
            result.skipped,
            result.orphans,
        )

    def close(self) -> None:
        self._stop_worker()
        if self.watcher is not None:
            self.watcher.stop()
            self.watcher = None
        if self.conn is not None:
            self.conn.close()
            self.conn = None


def _active_model_info(state: AppState) -> tuple[str | None, int | None]:
    if state.conn is None:
        return None, None
    return store.current_model_id(state.conn), store.current_dim(state.conn)


def create_app(state: AppState) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        state.open()
        try:
            yield
        finally:
            state.close()

    app = FastAPI(title="everlingo indexer", lifespan=lifespan)
    app.state.indexer = state

    @app.post("/search", response_model=SearchResponse)
    def do_search(req: SearchRequest) -> SearchResponse:
        start = time.perf_counter()
        hits = search.search(
            state.conn,  # type: ignore[arg-type]
            req.q,
            embedder=state.embedder,
            lang=req.lang,
            item_type=req.item_type,
            tags=req.tags,
            kind=req.kind,
            mode=req.mode,
            limit=req.limit,
        )
        took_ms = (time.perf_counter() - start) * 1000.0
        return SearchResponse(hits=hits, count=len(hits), took_ms=took_ms)

    @app.post("/index", response_model=OkResponse)
    def do_index(req: IndexRequest) -> OkResponse:
        abs_path = (state.memory_root / req.path).resolve()
        if not abs_path.exists():
            raise HTTPException(status_code=404, detail=f"file not found: {req.path}")
        try:
            parsed = parse_file(abs_path, state.memory_root)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"parse error: {e}")
        index_file(state.conn, parsed)  # type: ignore[arg-type]
        # 唤醒 worker 处理新增 chunk
        if state.worker is not None:
            state.worker.wake()
        return OkResponse(ok=True)

    @app.post("/delete", response_model=OkResponse)
    def do_delete(req: IndexRequest) -> OkResponse:
        ok = delete_file(state.conn, req.path)  # type: ignore[arg-type]
        return OkResponse(ok=ok)

    @app.post("/rebuild", response_model=RebuildResponse)
    def do_rebuild() -> RebuildResponse:
        start = time.perf_counter()
        # 清 documents + documents_fts（虚拟表无 FK CASCADE）+ chunks
        # 顺序：先清 FTS（独立），再清 documents（chunks 跟随 CASCADE）
        state.conn.execute("DELETE FROM documents_fts")  # type: ignore[union-attr]
        state.conn.execute("DELETE FROM documents")  # type: ignore[union-attr]
        # chunk_embeddings 由 CASCADE 清；vec0 由触发器同步清
        state.conn.commit()  # type: ignore[union-attr]
        result = reconcile(state.conn, state.memory_root)  # type: ignore[arg-type]
        # 清 vec0 孤儿（DELETE FROM documents → chunks CASCADE → chunk_embeddings CASCADE）
        try:
            store.prune_orphan_vec_rows(state.conn)  # type: ignore[arg-type]
        except Exception as e:
            logger.debug("prune_orphan_vec_rows 失败: %s", e)
        if state.worker is not None:
            state.worker.wake()
        took_ms = (time.perf_counter() - start) * 1000.0
        return RebuildResponse(
            ok=True,
            indexed=result.indexed,
            chunks=count_chunks(state.conn),  # type: ignore[arg-type]
            took_ms=took_ms,
        )

    @app.post("/embed", response_model=EmbedResponse)
    def do_embed(req: EmbedRequest) -> EmbedResponse:
        start = time.perf_counter()
        if state.embedder is None or state.worker is None:
            return EmbedResponse(
                ok=False,
                total_chunks=count_chunks(state.conn),  # type: ignore[arg-type]
                embedded_chunks=0,
                embedding_model_id=None,
                embedding_dim=None,
                took_ms=(time.perf_counter() - start) * 1000.0,
            )
        model_id, dim = _active_model_info(state)
        if req.rebuild and model_id is not None and dim is not None:
            # 全量重嵌（drop + 全量）
            state._stop_worker()  # type: ignore[attr-defined]
            store.rebuild_for_model(
                state.conn,  # type: ignore[arg-type]
                model_id,
                dim,
                state.embedder,
                batch=req.batch,
            )
            state._start_worker()  # type: ignore[attr-defined]
        elif req.wait:
            # 同步等到全量嵌入完成（按当前 batch 跑空）
            embedded = 0
            while True:
                pending = store.pending_chunk_ids(
                    state.conn,  # type: ignore[arg-type]
                    model_id=state.worker.model_id,
                    limit=req.batch,
                )
                if not pending:
                    break
                n = store.batch_upsert(
                    state.conn,  # type: ignore[arg-type]
                    pending,
                    state.embedder,
                    model_id=state.worker.model_id,
                    dim=state.worker.dim,
                )
                try:
                    store.prune_orphan_vec_rows(state.conn)  # type: ignore[arg-type]
                except Exception as e:
                    logger.debug("prune_orphan_vec_rows 失败: %s", e)
                state.conn.commit()  # type: ignore[union-attr]
                embedded += n
        else:
            state.worker.wake()

        embedded_chunks = 0
        if state.worker is not None:
            embedded_chunks = store.count_embedded(
                state.conn,  # type: ignore[arg-type]
                model_id=state.worker.model_id,
            )
        took_ms = (time.perf_counter() - start) * 1000.0
        return EmbedResponse(
            ok=True,
            embedded=0,
            total_chunks=count_chunks(state.conn),  # type: ignore[arg-type]
            embedded_chunks=embedded_chunks,
            embedding_model_id=state.worker.model_id if state.worker else None,
            embedding_dim=state.worker.dim if state.worker else None,
            took_ms=took_ms,
        )

    @app.get("/status", response_model=StatusResponse)
    def do_status() -> StatusResponse:
        model_id, dim = _active_model_info(state)
        embedded_chunks = 0
        if model_id is not None:
            embedded_chunks = store.count_embedded(state.conn, model_id=model_id)  # type: ignore[arg-type]
        return StatusResponse(
            running=True,
            tokenizer_version=tokenizer_version(),
            docs=count_docs(state.conn),  # type: ignore[arg-type]
            chunks=count_chunks(state.conn),  # type: ignore[arg-type]
            uptime_s=time.time() - state.started_at,
            embedding_model_id=model_id,
            embedding_dim=dim,
            embedded_chunks=embedded_chunks,
        )

    return app


# ── uvicorn 入口 ─────────────────────────────────────────────────────


def run_server() -> FastAPI:
    """uvicorn --factory 入口；零参。

    workspace 路径来自已 init 的 workspace 模块（由 cli.cmd_indexer_start
    在调用前 init）。
    返回 ASGI app（uvicorn 用作 ASGI handler）。
    """
    from .... import workspace  # everlingo.mem.vault.search → everlingo

    db_path = workspace.index_db_path()
    memory_root = workspace.vault_dir()
    socket_path = workspace.indexer_socket_path()
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    if socket_path.exists():
        socket_path.unlink()
    state = AppState(db_path=db_path, memory_root=memory_root, socket_path=socket_path)
    return create_app(state)


def _run_indexer(log_level: str = "info", log_path: Path | None = None) -> int:
    """在当前进程内直接运行 uvicorn（前台阻塞，不开子进程）。

    workspace 路径来自已 init 的 workspace 模块（由 cli.cmd_indexer_start
    在调用前 init）。log_path 传入时把 uvicorn 日志重定向到该文件
    （$workspace/logs/indexer.log）；不传则走 uvicorn 默认 stderr。
    阻塞直至收到信号退出。返回 0。
    """
    import logging.config

    import uvicorn as _uvicorn

    from .... import workspace

    socket_path = workspace.indexer_socket_path()
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    if socket_path.exists():
        socket_path.unlink()
    app = run_server()
    kwargs: dict = dict(
        uds=str(socket_path),
        log_level=log_level,
        access_log=False,
        lifespan="on",
    )
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        kwargs["log_config"] = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)s [%(name)s] %(message)s",
                },
            },
            "handlers": {
                "file": {
                    "class": "logging.FileHandler",
                    "formatter": "default",
                    "filename": str(log_path),
                    "mode": "a",
                    "encoding": "utf-8",
                },
            },
            "root": {"handlers": ["file"], "level": log_level.upper()},
            "loggers": {
                "uvicorn": {"handlers": ["file"], "level": log_level.upper(), "propagate": False},
                "uvicorn.error": {"handlers": ["file"], "level": log_level.upper(), "propagate": False},
                "uvicorn.access": {"handlers": ["file"], "level": log_level.upper(), "propagate": False},
            },
        }
    _uvicorn.run(app, **kwargs)
    return 0
