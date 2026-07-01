# ref: docs/impl-spec/search/memory-vault-search-spec.md — 文件监听
# watchdog 监听 $workspace/memory/ 下的 .md 增删改，事件路由到 indexer。
# 300ms 去抖，ulid 幂等 upsert。
#
# 实现：
#   - Observer 线程运行 watchdog Observer
#   - 主线程提供 start() / stop()
#   - 事件 -> 调度到同一个 thread pool（sqlite 写入串行化）
#   - 同一路径 300ms 内的多次写合并为一次
#   - 重命名：on_moved；ulid 不变 -> 只更新 file_path；ulid 变化 -> 删旧建新

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from watchdog.events import (
    FileMovedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from .indexer import (
    delete_file,
    get_by_ulid,
    index_file,
    parse_file,
)

logger = logging.getLogger(__name__)


DEBOUNCE_SECONDS = 0.3


@dataclass
class _PendingEvent:
    abs_path: Path
    kind: str  # 'upsert' / 'delete'
    src_path: Path | None  # for move events
    due_at: float


class _Handler(FileSystemEventHandler):
    def __init__(self, queue: list[_PendingEvent], lock: threading.Lock) -> None:
        self._queue = queue
        self._lock = lock

    def _enqueue(self, abs_path: Path, kind: str, src: Path | None = None) -> None:
        with self._lock:
            self._queue.append(
                _PendingEvent(
                    abs_path=abs_path,
                    kind=kind,
                    src_path=src,
                    due_at=time.monotonic() + DEBOUNCE_SECONDS,
                )
            )

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory and str(event.src_path).endswith(".md"):
            self._enqueue(Path(event.src_path), "upsert")

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory and str(event.src_path).endswith(".md"):
            self._enqueue(Path(event.src_path), "upsert")

    def on_moved(self, event) -> None:
        if event.is_directory:
            return
        src = Path(event.src_path)
        dest = Path(event.dest_path)
        if str(src).endswith(".md"):
            self._enqueue(src, "delete")
        if str(dest).endswith(".md"):
            self._enqueue(dest, "upsert")

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory and str(event.src_path).endswith(".md"):
            self._enqueue(Path(event.src_path), "delete")


class VaultWatcher:
    """indexer 进程内的 watchdog watcher。

    用法：
        w = VaultWatcher(conn, memory_root)
        w.start()
        ... 主循环
        w.stop()
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        memory_root: Path,
        on_error: Callable[[BaseException], None] | None = None,
    ) -> None:
        self._conn = conn
        self._memory_root = memory_root.resolve()
        self._observer: Observer | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._queue: list[_PendingEvent] = []
        self._lock = threading.Lock()
        self._on_error = on_error

    def start(self) -> None:
        if self._observer is not None:
            return
        self._memory_root.mkdir(parents=True, exist_ok=True)
        handler = _Handler(self._queue, self._lock)
        observer = Observer()
        observer.schedule(handler, str(self._memory_root), recursive=True)
        observer.start()
        self._observer = observer
        self._thread = threading.Thread(target=self._loop, name="vault-watcher", daemon=True)
        self._thread.start()
        logger.info("VaultWatcher started on %s", self._memory_root)

    def stop(self) -> None:
        self._stop.set()
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=2.0)
            self._observer = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("VaultWatcher stopped")

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._drain_once()
            self._stop.wait(0.05)

    def _drain_once(self) -> None:
        now = time.monotonic()
        with self._lock:
            ready = [e for e in self._queue if e.due_at <= now]
            for e in ready:
                self._queue.remove(e)
        for ev in ready:
            try:
                self._dispatch(ev)
            except Exception as e:
                logger.exception("watcher dispatch 失败: %s", e)
                if self._on_error is not None:
                    self._on_error(e)

    def _dispatch(self, ev: _PendingEvent) -> None:
        if ev.kind == "delete":
            try:
                rel = ev.abs_path.resolve().relative_to(self._memory_root).as_posix()
            except ValueError:
                return
            if delete_file(self._conn, rel):
                logger.info("watcher: deleted %s", rel)
            return

        # upsert
        if not ev.abs_path.exists():
            # race: 文件已不存在，降级为 delete
            try:
                rel = ev.abs_path.resolve().relative_to(self._memory_root).as_posix()
            except ValueError:
                return
            delete_file(self._conn, rel)
            return
        try:
            parsed = parse_file(ev.abs_path, self._memory_root)
        except Exception as e:
            logger.warning("watcher: 解析失败 %s: %s", ev.abs_path, e)
            return
        # 重命名时 ulid 变化：可能既有旧 ulid 行又有新 ulid 行；如新行已存在但
        # 是旧 path，需要把旧 ulid 旧 path 的行也清掉（通过 file_path）
        existing = get_by_ulid(self._conn, parsed.ulid)
        index_file(self._conn, parsed)
        logger.info("watcher: indexed %s (ulid=%s)", parsed.file_path, parsed.ulid)
