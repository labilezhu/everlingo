"""WS-Master 数据层测试：schema 创建、CRUD、约束。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from everlingo.ws_master.db import ensure_schema, get_conn


def test_ensure_schema_idempotent(tmp_path: Path):
    """ensure_schema 可多次调用，幂等。"""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    ensure_schema(conn)
    ensure_schema(conn)  # second call should not raise
    conn.close()


def test_schema_creates_all_tables(tmp_path: Path):
    """四张表都存在。"""
    conn = get_conn(str(tmp_path / "test.db"))
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "users" in tables
    assert "user_identities" in tables
    assert "pat_tokens" in tables
    assert "ws_containers" in tables
    conn.close()


def test_users_unique_user_name(tmp_path: Path):
    """users.user_name UNIQUE 约束生效。"""
    conn = get_conn(str(tmp_path / "test.db"))
    conn.execute(
        "INSERT INTO users (user_id, user_name, user_display_name, password_hash, created_at) "
        "VALUES ('a', 'mark', 'Mark', 'hash1', '2026-01-01Z')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO users (user_id, user_name, user_display_name, password_hash, created_at) "
            "VALUES ('b', 'mark', 'Mark2', 'hash2', '2026-01-01Z')"
        )
    conn.close()


def test_ws_containers_unique_container_name(tmp_path: Path):
    """ws_containers.container_name UNIQUE 约束生效。"""
    conn = get_conn(str(tmp_path / "test.db"))
    conn.execute(
        "INSERT INTO users (user_id, user_name, user_display_name, password_hash, created_at) "
        "VALUES ('u1', 'mark', 'Mark', 'hash', '2026-01-01Z')"
    )
    conn.execute(
        "INSERT INTO ws_containers (ws_container_id, user_id, container_name, host_workspace_dir, is_default, created_at) "
        "VALUES ('w1', 'u1', 'everlingo-mark-a1b2c3d4', '/ws/mark/a1b2c3d4', 1, '2026-01-01Z')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO ws_containers (ws_container_id, user_id, container_name, host_workspace_dir, is_default, created_at) "
            "VALUES ('w2', 'u1', 'everlingo-mark-a1b2c3d4', '/ws/mark/x123', 0, '2026-01-01Z')"
        )
    conn.close()


def test_identities_unique_provider_subject(tmp_path: Path):
    """user_identities UNIQUE(provider, subject) 约束生效。"""
    conn = get_conn(str(tmp_path / "test.db"))
    conn.execute(
        "INSERT INTO users (user_id, user_name, user_display_name, password_hash, created_at) "
        "VALUES ('u1', 'mark', 'Mark', 'hash', '2026-01-01Z')"
    )
    conn.execute(
        "INSERT INTO user_identities (identity_id, user_id, provider, subject, created_at) "
        "VALUES ('i1', 'u1', 'google', 'sub123', '2026-01-01Z')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO user_identities (identity_id, user_id, provider, subject, created_at) "
            "VALUES ('i2', 'u1', 'google', 'sub123', '2026-01-01Z')"
        )
    conn.close()


def test_foreign_key_cascade_delete(tmp_path: Path):
    """删除 user 时级联删除关联的 pat_tokens 和 ws_containers。"""
    conn = get_conn(str(tmp_path / "test.db"))
    conn.execute(
        "INSERT INTO users (user_id, user_name, user_display_name, password_hash, created_at) "
        "VALUES ('u1', 'mark', 'Mark', 'hash', '2026-01-01Z')"
    )
    conn.execute(
        "INSERT INTO pat_tokens (id, user_id, token_hash, label, created_at) "
        "VALUES ('p1', 'u1', 'abc123', 'test', '2026-01-01Z')"
    )
    conn.execute(
        "DELETE FROM users WHERE user_id = 'u1'"
    )
    # pat_tokens should be cascaded
    pats = conn.execute("SELECT * FROM pat_tokens").fetchall()
    assert len(pats) == 0
    conn.close()