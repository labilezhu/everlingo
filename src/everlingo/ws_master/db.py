"""SQLite 数据库 schema 创建与迁移。

幂等地创建四张表：users, user_identities, pat_tokens, ws_containers。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    user_name TEXT NOT NULL UNIQUE,
    user_display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    openai_api_key TEXT,
    openai_base_url TEXT,
    openai_model TEXT,
    openai_embedding_model TEXT
);

CREATE TABLE IF NOT EXISTS user_identities (
    identity_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    subject TEXT NOT NULL,
    email TEXT,
    display_name TEXT,
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    UNIQUE(provider, subject)
);

CREATE INDEX IF NOT EXISTS idx_identities_user_id ON user_identities(user_id);
CREATE INDEX IF NOT EXISTS idx_identities_provider_subject ON user_identities(provider, subject);

CREATE TABLE IF NOT EXISTS pat_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,
    label TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    expires_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_pat_user_id ON pat_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_pat_token_hash ON pat_tokens(token_hash);

CREATE TABLE IF NOT EXISTS ws_containers (
    ws_container_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    container_name TEXT NOT NULL UNIQUE,
    docker_container_id TEXT,
    status TEXT NOT NULL DEFAULT 'absent',
    host_workspace_dir TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    last_seen_at TEXT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_ws_user_id ON ws_containers(user_id);
CREATE INDEX IF NOT EXISTS idx_ws_status ON ws_containers(status);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tables if not exist. Idempotent."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def get_conn(db_path: str | Path) -> sqlite3.Connection:
    """Open or create the SQLite database and ensure schema exists."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)
    return conn