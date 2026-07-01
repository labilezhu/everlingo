# ref: docs/impl-spec/search/memory-vault-search-spec.md — IPC 协议 / server.py
# FastAPI app + uvicorn --uds $workspace/index/indexer.sock 入口。
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
from .indexer import (
    count_chunks,
    count_docs,
    delete_file,
    index_file,
    parse_file,
    set_meta,
)
from .protocol import (
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

    def open(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.memory_root.mkdir(parents=True, exist_ok=True)
        self.conn = open_db(self.db_path)
        # 启动对账
        result = reconcile(self.conn, self.memory_root)
        # 启动 watcher
        self.watcher = VaultWatcher(self.conn, self.memory_root)
        self.watcher.start()
        logger.info(
            "indexer ready: db=%s sock=%s reconcile indexed=%d skipped=%d orphans=%d",
            self.db_path,
            self.socket_path,
            result.indexed,
            result.skipped,
            result.orphans,
        )

    def close(self) -> None:
        if self.watcher is not None:
            self.watcher.stop()
            self.watcher = None
        if self.conn is not None:
            self.conn.close()
            self.conn = None


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
        state.conn.commit()  # type: ignore[union-attr]
        result = reconcile(state.conn, state.memory_root)  # type: ignore[arg-type]
        took_ms = (time.perf_counter() - start) * 1000.0
        return RebuildResponse(
            ok=True,
            indexed=result.indexed,
            chunks=count_chunks(state.conn),  # type: ignore[arg-type]
            took_ms=took_ms,
        )

    @app.get("/status", response_model=StatusResponse)
    def do_status() -> StatusResponse:
        return StatusResponse(
            running=True,
            tokenizer_version=tokenizer_version(),
            docs=count_docs(state.conn),  # type: ignore[arg-type]
            chunks=count_chunks(state.conn),  # type: ignore[arg-type]
            uptime_s=time.time() - state.started_at,
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
    memory_root = workspace.memory_dir()
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
