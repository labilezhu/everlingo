# ref: docs/impl-spec/search/memory-vault-search-spec.md — 同步策略 / 启动对账
# indexer 启动时扫一遍 vault，用 file_mtime + content_hash 对账：
#   - 文件不在 documents 中 -> 新增索引
#   - 文件 hash 变化 -> 更新
#   - documents 有但 vault 无 -> 清孤儿
# 比对 meta.tokenizer_version，版本变化则全量重建 FTS（FTS 重建便宜）。

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from .indexer import (
    count_chunks,
    count_docs,
    delete_file,
    get_by_ulid,
    get_meta,
    index_file,
    init_db,
    parse_file,
    rebuild_fts,
    set_meta,
)
from .tokenizer import tokenizer_version

logger = logging.getLogger(__name__)


@dataclass
class ReconcileResult:
    indexed: int  # 新增 / 更新文件数
    skipped: int  # content_hash 未变跳过数
    orphans: int  # 清孤儿行数
    fts_rebuilt: bool
    took_ms: float


def open_db(db_path: Path) -> sqlite3.Connection:
    """打开 SQLite 连接，启用 WAL + foreign keys；DB 不存在时自动 init。

    check_same_thread=False 因为 SQLite 连接会被 FastAPI TestClient / uvicorn
    的 worker 线程共享。indexer 进程内仍以单线程为主（FastAPI sync 路由），
    不存在并发写问题；如需异步 worker，再加锁。
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # 首次启动：建表
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='documents'"
    ).fetchone()
    if cur is None:
        init_db(conn)
    return conn


def reconcile(conn: sqlite3.Connection, memory_root: Path) -> ReconcileResult:
    """全量对账。memory_root 已 resolve 过的绝对路径。"""
    start = time.perf_counter()
    indexed = 0
    skipped = 0
    orphans = 0

    # 1) tokenizer 版本比对
    current_ver = tokenizer_version()
    stored_ver = get_meta(conn, "tokenizer_version")
    fts_rebuilt = False
    if stored_ver is not None and stored_ver != current_ver:
        logger.info("tokenizer_version 变化 (%s -> %s)，全量重建 FTS", stored_ver, current_ver)
        rebuild_fts(conn)
        fts_rebuilt = True
    set_meta(conn, "tokenizer_version", current_ver)

    # 2) 扫 vault：每文件 -> 比对 ulid/合成键 查 (rowid, content_hash)
    seen_paths: set[str] = set()
    for abs_path in memory_root.rglob("*.md"):
        if not abs_path.is_file():
            continue
        try:
            parsed = parse_file(abs_path, memory_root)
        except Exception as e:
            logger.warning("解析失败，跳过 %s: %s", abs_path, e)
            continue
        seen_paths.add(parsed.file_path)
        existing = get_by_ulid(conn, parsed.ulid)
        if existing is not None:
            _, old_hash = existing
            if old_hash == parsed.content_hash:
                skipped += 1
                continue
        index_file(conn, parsed)
        indexed += 1

    # 3) 清孤儿：documents.file_path 不在 seen_paths 中的行
    rows = conn.execute("SELECT file_path FROM documents").fetchall()
    for (file_path,) in rows:
        if file_path not in seen_paths:
            delete_file(conn, file_path)
            orphans += 1

    took_ms = (time.perf_counter() - start) * 1000.0
    logger.info(
        "reconcile: indexed=%d skipped=%d orphans=%d fts_rebuilt=%s took=%.2fms "
        "docs=%d chunks=%d",
        indexed,
        skipped,
        orphans,
        fts_rebuilt,
        took_ms,
        count_docs(conn),
        count_chunks(conn),
    )
    return ReconcileResult(
        indexed=indexed,
        skipped=skipped,
        orphans=orphans,
        fts_rebuilt=fts_rebuilt,
        took_ms=took_ms,
    )
