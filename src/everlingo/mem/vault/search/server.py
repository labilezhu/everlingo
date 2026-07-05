# ref: docs/impl-spec/search/memory-vault-search-spec.md — IPC 协议 / server.py
# FastAPI app + uvicorn --uds $workspace/indexer.sock 入口。
# 所有端点通过 path segment /{lang}/... 路由到对应语言的 DB。
# indexer 进程内 import；gateway 进程不加载本文件。

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Path as PathParam
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

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
    LangStatus,
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


class LangState:
    """单语言的 indexer 子状态。"""

    def __init__(self, lang: str, db_path: Path, memory_root: Path) -> None:
        self.lang = lang
        self.db_path = db_path
        self.memory_root = memory_root
        self.conn: sqlite3.Connection | None = None
        self.watcher: VaultWatcher | None = None
        self.embedder = None
        self.worker: EmbeddingWorker | None = None

    def _init_embedder(self) -> None:
        """尝试构造 embedder。失败（模型未配）则保持 None，FTS 不受影响。"""
        try:
            self.embedder = AIEmbedding.create()
        except ValueError as e:
            logger.info("[%s] embedder 未启用: %s（semantic/hybrid 模式将降级）", self.lang, e)
            self.embedder = None
        except Exception as e:
            logger.warning("[%s] 构造 embedder 失败: %s", self.lang, e)
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
                logger.warning("[%s] 探测 embedding 维度失败: %s", self.lang, e)
                return
            model_id = self.embedder.model
            store.set_current_model(self.conn, model_id, dim)
        # vec0 扩展未生效 → 不起 worker
        if not store.vec0_available(self.conn):
            logger.info("[%s] vec0 不可用，embedding worker 不启动", self.lang)
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
        result = reconcile(self.conn, self.memory_root, self.lang)
        # 启动 watcher
        self.watcher = VaultWatcher(self.conn, self.memory_root, self.lang)
        self.watcher.start()
        # 启动 embedding worker
        self._init_embedder()
        self._start_worker()
        logger.info(
            "[%s] indexer ready: db=%s reconcile indexed=%d skipped=%d orphans=%d",
            self.lang,
            self.db_path,
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


class _LangDiscoveryHandler(FileSystemEventHandler):
    """LangDiscoveryWatcher 的 watchdog handler。

    监听 `$workspace/memory/languages/` 下的目录创建事件，仅响应
    `*/vault/` 出现的情况（lang 根目录先建、vault 后建时，等 vault 出现
    再触发；文件创建事件忽略）。
    """

    def __init__(self, app_state: "AppState") -> None:
        self._app_state = app_state

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            path = Path(event.src_path)
            if path.name == "vault":
                lang = path.parent.name
                if lang:
                    try:
                        self._app_state._open_lang(lang)
                    except Exception as e:  # noqa: BLE001
                        logger.warning(
                            "LangDiscoveryWatcher: open lang=%s 失败: %s", lang, e
                        )


class LangDiscoveryWatcher:
    """顶层 lang 发现 watcher。

    监听 `$workspace/memory/languages/`，检测新 lang 目录的 `vault/`
    子目录出现，并触发 `AppState._open_lang(lang)`。与端点懒加载共享
    同一加锁 open 路径（已注册的 lang 不会重复打开）。
    """

    def __init__(self, app_state: "AppState", languages_dir: Path) -> None:
        self._app_state = app_state
        self._languages_dir = languages_dir
        self._observer: Observer | None = None

    def start(self) -> None:
        if self._observer is not None:
            return
        self._languages_dir.mkdir(parents=True, exist_ok=True)
        handler = _LangDiscoveryHandler(self._app_state)
        observer = Observer()
        # recursive=True：需要捕到 `ja/vault/` 这种嵌套子目录的创建
        # 事件；inotify 限制下，languages/ 子树不深（每 lang 一个 vault/），
        # 监听成本可接受。handler 内部对非 `*/vault/` 事件做过滤。
        observer.schedule(handler, str(self._languages_dir), recursive=True)
        observer.start()
        self._observer = observer
        logger.info("LangDiscoveryWatcher started on %s", self._languages_dir)

    def stop(self) -> None:
        if self._observer is None:
            return
        self._observer.stop()
        self._observer.join(timeout=2.0)
        self._observer = None
        logger.info("LangDiscoveryWatcher stopped")


class AppState:
    """indexer 进程内的全局状态（FastAPI lifespan 注入）。

    持有 N 个 LangState（每语言一个），通过 lang 路由到对应 DB。
    启动时按 `_langs_to_open` 打开已知 lang；启动后通过顶层
    LangDiscoveryWatcher 监听 `memory/languages/` 下的新 `vault/` 目录
    自动开新 lang；端点 miss 时也会懒加载开新 lang（vault 目录存在的前提）。
    """

    def __init__(self, socket_path: Path, langs: list[str] | None = None) -> None:
        from .... import workspace

        self.socket_path = socket_path
        self.started_at = time.time()
        self._lang_states: dict[str, LangState] = {}
        self._lock = threading.Lock()
        self._discovery_watcher: LangDiscoveryWatcher | None = None
        self._langs_to_open = langs or workspace.lang_dirs()

    def _open_lang(self, lang: str) -> LangState:
        """加锁打开 lang state。已注册直接返回；vault 目录不存在 → 404。

        端点懒加载、启动批量 open、LangDiscoveryWatcher 三路都走这里。
        """
        from .... import workspace

        with self._lock:
            state = self._lang_states.get(lang)
            if state is not None:
                return state
            db_path = workspace.lang_index_dir(lang) / "memory.sqlite"
            memory_root = workspace.lang_vault_dir(lang)
            if not memory_root.is_dir():
                raise HTTPException(
                    status_code=404, detail=f"lang not found: {lang}"
                )
            lang_state = LangState(lang, db_path, memory_root)
            lang_state.open()
            self._lang_states[lang] = lang_state
            return lang_state

    def _get_lang_state(self, lang: str) -> LangState:
        try:
            return self._open_lang(lang)
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            logger.exception("_open_lang(%s) 失败: %s", lang, e)
            raise HTTPException(status_code=500, detail=f"open lang failed: {lang}: {e}")

    def open(self) -> None:
        from .... import workspace

        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        for lang in self._langs_to_open:
            try:
                self._open_lang(lang)
            except HTTPException as e:
                logger.warning("启动时打开 lang=%s 失败: %s", lang, e.detail)
        # 启动 lang 发现 watcher（监听 memory/languages/ 下的新 vault/）
        languages_dir = workspace.memory_dir() / "languages"
        self._discovery_watcher = LangDiscoveryWatcher(self, languages_dir)
        self._discovery_watcher.start()

    def close(self) -> None:
        if self._discovery_watcher is not None:
            self._discovery_watcher.stop()
            self._discovery_watcher = None
        for lang_state in self._lang_states.values():
            lang_state.close()
        self._lang_states.clear()


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

    @app.get("/status", response_model=StatusResponse)
    def do_status() -> StatusResponse:
        lang_statuses = []
        for lang, ls in sorted(state._lang_states.items()):
            if ls.conn is None:
                continue
            model_id = store.current_model_id(ls.conn)
            dim = store.current_dim(ls.conn)
            embedded_chunks = 0
            if model_id is not None:
                embedded_chunks = store.count_embedded(ls.conn, model_id=model_id)
            lang_statuses.append(LangStatus(
                lang=lang,
                tokenizer_version=tokenizer_version(),
                docs=count_docs(ls.conn),
                chunks=count_chunks(ls.conn),
                embedded_chunks=embedded_chunks,
                embedding_model_id=model_id,
            ))
        return StatusResponse(
            running=True,
            uptime_s=time.time() - state.started_at,
            langs=lang_statuses,
        )

    @app.post("/{lang}/search", response_model=SearchResponse)
    def do_search(lang: str, req: SearchRequest) -> SearchResponse:
        ls = state._get_lang_state(lang)
        start = time.perf_counter()
        hits = search.search(
            ls.conn,  # type: ignore[arg-type]
            req.q,
            lang=lang,
            embedder=ls.embedder,
            item_type=req.item_type,
            tags=req.tags,
            kind=req.kind,
            mode=req.mode,
            limit=req.limit,
        )
        took_ms = (time.perf_counter() - start) * 1000.0
        return SearchResponse(hits=hits, count=len(hits), took_ms=took_ms)

    @app.post("/{lang}/index", response_model=OkResponse)
    def do_index(lang: str, req: IndexRequest) -> OkResponse:
        ls = state._get_lang_state(lang)
        abs_path = (ls.memory_root / req.path).resolve()
        if not abs_path.exists():
            raise HTTPException(status_code=404, detail=f"file not found: {req.path}")
        try:
            parsed = parse_file(abs_path, ls.memory_root, lang)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"parse error: {e}")
        index_file(ls.conn, parsed)  # type: ignore[arg-type]
        # 唤醒 worker 处理新增 chunk
        if ls.worker is not None:
            ls.worker.wake()
        return OkResponse(ok=True)

    @app.post("/{lang}/delete", response_model=OkResponse)
    def do_delete(lang: str, req: IndexRequest) -> OkResponse:
        ls = state._get_lang_state(lang)
        ok = delete_file(ls.conn, req.path)  # type: ignore[arg-type]
        return OkResponse(ok=ok)

    @app.post("/{lang}/rebuild", response_model=RebuildResponse)
    def do_rebuild(lang: str) -> RebuildResponse:
        ls = state._get_lang_state(lang)
        start = time.perf_counter()
        ls.conn.execute("DELETE FROM documents_fts")  # type: ignore[union-attr]
        ls.conn.execute("DELETE FROM documents")  # type: ignore[union-attr]
        ls.conn.commit()  # type: ignore[union-attr]
        result = reconcile(ls.conn, ls.memory_root, lang)  # type: ignore[arg-type]
        try:
            store.prune_orphan_vec_rows(ls.conn)  # type: ignore[arg-type]
        except Exception as e:
            logger.debug("[%s] prune_orphan_vec_rows 失败: %s", lang, e)
        if ls.worker is not None:
            ls.worker.wake()
        took_ms = (time.perf_counter() - start) * 1000.0
        return RebuildResponse(
            ok=True,
            indexed=result.indexed,
            chunks=count_chunks(ls.conn),  # type: ignore[arg-type]
            took_ms=took_ms,
        )

    @app.post("/{lang}/embed", response_model=EmbedResponse)
    def do_embed(lang: str, req: EmbedRequest) -> EmbedResponse:
        ls = state._get_lang_state(lang)
        start = time.perf_counter()
        if ls.embedder is None or ls.worker is None:
            return EmbedResponse(
                ok=False,
                total_chunks=count_chunks(ls.conn),  # type: ignore[arg-type]
                embedded_chunks=0,
                embedding_model_id=None,
                embedding_dim=None,
                took_ms=(time.perf_counter() - start) * 1000.0,
            )
        model_id = store.current_model_id(ls.conn)  # type: ignore[arg-type]
        dim = store.current_dim(ls.conn)  # type: ignore[arg-type]
        if req.rebuild and model_id is not None and dim is not None:
            ls._stop_worker()  # type: ignore[attr-defined]
            store.rebuild_for_model(
                ls.conn,  # type: ignore[arg-type]
                model_id,
                dim,
                ls.embedder,
                batch=req.batch,
            )
            ls._start_worker()  # type: ignore[attr-defined]
        elif req.wait:
            embedded = 0
            while True:
                pending = store.pending_chunk_ids(
                    ls.conn,  # type: ignore[arg-type]
                    model_id=ls.worker.model_id,
                    limit=req.batch,
                )
                if not pending:
                    break
                n = store.batch_upsert(
                    ls.conn,  # type: ignore[arg-type]
                    pending,
                    ls.embedder,
                    model_id=ls.worker.model_id,
                    dim=ls.worker.dim,
                )
                try:
                    store.prune_orphan_vec_rows(ls.conn)  # type: ignore[arg-type]
                except Exception as e:
                    logger.debug("[%s] prune_orphan_vec_rows 失败: %s", lang, e)
                ls.conn.commit()  # type: ignore[union-attr]
                embedded += n
        else:
            ls.worker.wake()

        embedded_chunks = 0
        if ls.worker is not None:
            embedded_chunks = store.count_embedded(
                ls.conn,  # type: ignore[arg-type]
                model_id=ls.worker.model_id,
            )
        took_ms = (time.perf_counter() - start) * 1000.0
        return EmbedResponse(
            ok=True,
            embedded=0,
            total_chunks=count_chunks(ls.conn),  # type: ignore[arg-type]
            embedded_chunks=embedded_chunks,
            embedding_model_id=ls.worker.model_id if ls.worker else None,
            embedding_dim=ls.worker.dim if ls.worker else None,
            took_ms=took_ms,
        )

    return app


# ── uvicorn 入口 ─────────────────────────────────────────────────────


def run_server() -> FastAPI:
    """uvicorn --factory 入口；零参。

    workspace 路径来自已 init 的 workspace 模块（由 cli.cmd_indexer_start
    在调用前 init）。
    返回 ASGI app（uvicorn 用作 ASGI handler）。
    """
    from .... import workspace

    socket_path = workspace.indexer_socket_path()
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    if socket_path.exists():
        socket_path.unlink()
    state = AppState(socket_path=socket_path)
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
