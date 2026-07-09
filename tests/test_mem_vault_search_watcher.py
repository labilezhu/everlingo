# ref: docs/impl-spec/search/memory-vault-search-spec.md — 文件监听
# watchdog 300ms 去抖 + ulid 幂等 upsert。
# 用真实 watchdog + tmp memory 跑端到端；等待超时用轮询。

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from everlingo.mem.vault.search.indexer import count_docs, init_db
from everlingo.mem.vault.search.watcher import DEBOUNCE_SECONDS, VaultWatcher


def _wait_until(predicate, timeout: float = 5.0, interval: float = 0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _write_item(memory_root: Path, name: str, ulid: str, body: str = "x") -> Path:
    """写 kb item 文件。新布局：不含 {lang}/ 前缀。"""
    p = memory_root / "items" / "vocab" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\nulid: {ulid}\nslug: {name.split('--')[0]}\ntype: vocab\n---\n\n{body}", encoding="utf-8")
    return p


def test_watcher_indexes_new_file(tmp_path: Path):
    db_path = tmp_path / "index" / "memory.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    memory_root = tmp_path / "memory"
    memory_root.mkdir()

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA foreign_keys=ON")
    init_db(conn)
    w = VaultWatcher(conn, memory_root, "en")
    w.start()
    try:
        p = _write_item(memory_root, "a--01JZW0001.md", "01JZW0001")
        ok = _wait_until(lambda: count_docs(conn) == 1, timeout=DEBOUNCE_SECONDS + 3.0)
        assert ok, "watcher did not index new file in time"
    finally:
        w.stop()
        conn.close()


def test_watcher_delete_removes_row(tmp_path: Path):
    db_path = tmp_path / "index" / "memory.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    memory_root = tmp_path / "memory"
    memory_root.mkdir()

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA foreign_keys=ON")
    init_db(conn)
    w = VaultWatcher(conn, memory_root, "en")
    w.start()
    try:
        p = _write_item(memory_root, "a--01JZW0002.md", "01JZW0002")
        assert _wait_until(lambda: count_docs(conn) == 1, timeout=DEBOUNCE_SECONDS + 3.0)

        p.unlink()
        ok = _wait_until(lambda: count_docs(conn) == 0, timeout=DEBOUNCE_SECONDS + 3.0)
        assert ok, "watcher did not remove row on delete in time"
    finally:
        w.stop()
        conn.close()


def test_watcher_skips_vault_spec_md(tmp_path: Path):
    """VAULT_SPEC.md（vault 元文件）写入不触发 watcher 索引。"""
    db_path = tmp_path / "index" / "memory.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    memory_root = tmp_path / "memory"
    memory_root.mkdir()

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA foreign_keys=ON")
    init_db(conn)
    w = VaultWatcher(conn, memory_root, "en")
    w.start()
    try:
        spec_p = memory_root / "VAULT_SPEC.md"
        spec_p.write_text("# spec\n", encoding="utf-8")
        assert _wait_until(lambda: count_docs(conn) == 0, timeout=DEBOUNCE_SECONDS + 2.0)
    finally:
        w.stop()
        conn.close()


def test_watcher_skips_spec_dir(tmp_path: Path):
    """spec/ 子目录下 .md 写入不触发 watcher 索引。"""
    db_path = tmp_path / "index" / "memory.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    memory_root = tmp_path / "memory"
    memory_root.mkdir()

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA foreign_keys=ON")
    init_db(conn)
    w = VaultWatcher(conn, memory_root, "en")
    w.start()
    try:
        spec_dir = memory_root / "spec"
        spec_dir.mkdir()
        (spec_dir / "vault_spec.md").write_text("# spec\n", encoding="utf-8")
        (spec_dir / "events_spec.md").write_text("# events\n", encoding="utf-8")
        assert _wait_until(lambda: count_docs(conn) == 0, timeout=DEBOUNCE_SECONDS + 2.0)
    finally:
        w.stop()
        conn.close()
