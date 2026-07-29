"""数据访问层（纯 CRUD，无业务逻辑）。

提供对 users/pat_tokens/ws_containers/user_identities 四张表的增删改查。
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class UserRow:
    user_id: str
    user_name: str
    user_display_name: str
    password_hash: str
    created_at: str
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    openai_model: Optional[str] = None
    openai_embedding_model: Optional[str] = None


@dataclass
class PatRow:
    id: str
    user_id: str
    token_hash: str
    label: str
    created_at: str
    last_used_at: Optional[str] = None
    expires_at: Optional[str] = None


@dataclass
class WsContainerRow:
    ws_container_id: str
    user_id: str
    container_name: str
    docker_container_id: Optional[str] = None
    status: str = "absent"
    host_workspace_dir: str = ""
    is_default: bool = False
    created_at: str = ""
    started_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class IdentityRow:
    identity_id: str
    user_id: str
    provider: str
    subject: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    created_at: str = ""
    last_used_at: Optional[str] = None


# ---------------------------------------------------------------------------
# UserRepo
# ---------------------------------------------------------------------------


class UserRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, user_name: str, display_name: str, password_hash: str) -> UserRow:
        user_id = _new_uuid()
        now = _now_iso()
        self._conn.execute(
            "INSERT INTO users (user_id, user_name, user_display_name, password_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, user_name, display_name, password_hash, now),
        )
        self._conn.commit()
        return self.get_by_id(user_id)

    def get_by_id(self, user_id: str) -> Optional[UserRow]:
        row = self._conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return _row_to_user(row) if row else None

    def get_by_name(self, user_name: str) -> Optional[UserRow]:
        row = self._conn.execute(
            "SELECT * FROM users WHERE user_name = ?", (user_name,)
        ).fetchone()
        return _row_to_user(row) if row else None

    def list_all(self) -> List[UserRow]:
        return [_row_to_user(r) for r in self._conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()]

    def delete(self, user_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        self._conn.commit()
        return cur.rowcount > 0


def _row_to_user(row: sqlite3.Row) -> UserRow:
    return UserRow(
        user_id=row["user_id"],
        user_name=row["user_name"],
        user_display_name=row["user_display_name"],
        password_hash=row["password_hash"],
        created_at=row["created_at"],
        openai_api_key=dict(row).get("openai_api_key"),
        openai_base_url=dict(row).get("openai_base_url"),
        openai_model=dict(row).get("openai_model"),
        openai_embedding_model=dict(row).get("openai_embedding_model"),
    )


# ---------------------------------------------------------------------------
# PatRepo
# ---------------------------------------------------------------------------


class PatRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, user_id: str, token_hash: str, label: str, expires_at: Optional[str] = None) -> PatRow:
        pat_id = _new_uuid()
        now = _now_iso()
        self._conn.execute(
            "INSERT INTO pat_tokens (id, user_id, token_hash, label, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (pat_id, user_id, token_hash, label, now, expires_at),
        )
        self._conn.commit()
        return self.get_by_id(pat_id)

    def get_by_id(self, pat_id: str) -> Optional[PatRow]:
        row = self._conn.execute(
            "SELECT * FROM pat_tokens WHERE id = ?", (pat_id,)
        ).fetchone()
        return _row_to_pat(row) if row else None

    def list_by_user(self, user_id: str) -> List[PatRow]:
        return [
            _row_to_pat(r)
            for r in self._conn.execute(
                "SELECT * FROM pat_tokens WHERE user_id = ? ORDER BY created_at", (user_id,)
            ).fetchall()
        ]

    def delete(self, pat_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM pat_tokens WHERE id = ?", (pat_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def verify(self, token_hash: str) -> Optional[PatRow]:
        """Find a PAT by hash, checking expiry."""
        row = self._conn.execute(
            "SELECT * FROM pat_tokens WHERE token_hash = ?", (token_hash,)
        ).fetchone()
        if row is None:
            return None
        pat = _row_to_pat(row)
        # Check expiry
        if pat.expires_at:
            now = _now_iso()
            if pat.expires_at < now:
                return None
        return pat

    def touch_last_used(self, pat_id: str) -> None:
        now = _now_iso()
        self._conn.execute(
            "UPDATE pat_tokens SET last_used_at = ? WHERE id = ?", (now, pat_id)
        )
        self._conn.commit()


def _row_to_pat(row: sqlite3.Row) -> PatRow:
    d = dict(row)
    return PatRow(
        id=d["id"],
        user_id=d["user_id"],
        token_hash=d["token_hash"],
        label=d["label"],
        created_at=d["created_at"],
        last_used_at=d.get("last_used_at"),
        expires_at=d.get("expires_at"),
    )


# ---------------------------------------------------------------------------
# WsContainerRepo
# ---------------------------------------------------------------------------


class WsContainerRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(
        self,
        user_id: str,
        container_name: str,
        host_workspace_dir: str,
        is_default: bool = False,
    ) -> WsContainerRow:
        ws_id = _new_uuid()
        now = _now_iso()
        self._conn.execute(
            "INSERT INTO ws_containers "
            "(ws_container_id, user_id, container_name, status, host_workspace_dir, is_default, created_at) "
            "VALUES (?, ?, ?, 'absent', ?, ?, ?)",
            (ws_id, user_id, container_name, host_workspace_dir, 1 if is_default else 0, now),
        )
        self._conn.commit()
        return self.get_by_id(ws_id)

    def get_by_id(self, ws_container_id: str) -> Optional[WsContainerRow]:
        row = self._conn.execute(
            "SELECT * FROM ws_containers WHERE ws_container_id = ?", (ws_container_id,)
        ).fetchone()
        return _row_to_ws(row) if row else None

    def get_by_container_name(self, container_name: str) -> Optional[WsContainerRow]:
        row = self._conn.execute(
            "SELECT * FROM ws_containers WHERE container_name = ?", (container_name,)
        ).fetchone()
        return _row_to_ws(row) if row else None

    def list_by_user(self, user_id: str) -> List[WsContainerRow]:
        return [
            _row_to_ws(r)
            for r in self._conn.execute(
                "SELECT * FROM ws_containers WHERE user_id = ? ORDER BY created_at", (user_id,)
            ).fetchall()
        ]

    def list_all(self) -> List[WsContainerRow]:
        return [
            _row_to_ws(r)
            for r in self._conn.execute("SELECT * FROM ws_containers ORDER BY created_at").fetchall()
        ]

    def list_by_status(self, *statuses: str) -> List[WsContainerRow]:
        placeholders = ",".join("?" for _ in statuses)
        return [
            _row_to_ws(r)
            for r in self._conn.execute(
                f"SELECT * FROM ws_containers WHERE status IN ({placeholders})",
                statuses,
            ).fetchall()
        ]

    def get_default(self, user_id: str) -> Optional[WsContainerRow]:
        row = self._conn.execute(
            "SELECT * FROM ws_containers WHERE user_id = ? AND is_default = 1", (user_id,)
        ).fetchone()
        return _row_to_ws(row) if row else None

    def set_default(self, ws_container_id: str, user_id: str) -> bool:
        """Set a ws-container as default for a user. Clears previous default first."""
        self._conn.execute(
            "UPDATE ws_containers SET is_default = 0 WHERE user_id = ?", (user_id,)
        )
        self._conn.execute(
            "UPDATE ws_containers SET is_default = 1 WHERE ws_container_id = ? AND user_id = ?",
            (ws_container_id, user_id),
        )
        self._conn.commit()
        return True

    def update_status(
        self,
        ws_container_id: str,
        status: str,
        *,
        docker_container_id: Optional[str] = None,
        error_message: Optional[str] = None,
        started_at: Optional[str] = None,
        last_seen_at: Optional[str] = None,
    ) -> bool:
        updates = ["status = ?"]
        params: list = [status]
        if docker_container_id is not None:
            updates.append("docker_container_id = ?")
            params.append(docker_container_id)
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)
        if started_at is not None:
            updates.append("started_at = ?")
            params.append(started_at)
        if last_seen_at is not None:
            updates.append("last_seen_at = ?")
            params.append(last_seen_at)
        params.append(ws_container_id)
        cur = self._conn.execute(
            f"UPDATE ws_containers SET {', '.join(updates)} WHERE ws_container_id = ?",
            params,
        )
        self._conn.commit()
        return cur.rowcount > 0

    def delete(self, ws_container_id: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM ws_containers WHERE ws_container_id = ?", (ws_container_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def count_by_user(self, user_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM ws_containers WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["cnt"] if row else 0


def _row_to_ws(row: sqlite3.Row) -> WsContainerRow:
    d = dict(row)
    return WsContainerRow(
        ws_container_id=d["ws_container_id"],
        user_id=d["user_id"],
        container_name=d["container_name"],
        docker_container_id=d.get("docker_container_id"),
        status=d["status"],
        host_workspace_dir=d["host_workspace_dir"],
        is_default=bool(d["is_default"]),
        created_at=d["created_at"],
        started_at=d.get("started_at"),
        last_seen_at=d.get("last_seen_at"),
        error_message=d.get("error_message"),
    )


# ---------------------------------------------------------------------------
# IdentityRepo
# ---------------------------------------------------------------------------


class IdentityRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_by_user(self, user_id: str) -> List[IdentityRow]:
        return [
            _row_to_identity(r)
            for r in self._conn.execute(
                "SELECT * FROM user_identities WHERE user_id = ? ORDER BY created_at",
                (user_id,),
            ).fetchall()
        ]

    def unlink(self, identity_id: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM user_identities WHERE identity_id = ?", (identity_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0


def _row_to_identity(row: sqlite3.Row) -> IdentityRow:
    d = dict(row)
    return IdentityRow(
        identity_id=d["identity_id"],
        user_id=d["user_id"],
        provider=d["provider"],
        subject=d["subject"],
        email=d.get("email"),
        display_name=d.get("display_name"),
        created_at=d["created_at"],
        last_used_at=d.get("last_used_at"),
    )