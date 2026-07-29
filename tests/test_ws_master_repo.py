"""WS-Master 数据访问层测试：CRUD 操作。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from everlingo.ws_master.db import get_conn
from everlingo.ws_master.repo import (
    IdentityRepo,
    PatRepo,
    UserRepo,
    WsContainerRepo,
)


@pytest.fixture
def repos(tmp_path: Path):
    """Create repos with fresh sqlite DB."""
    conn = get_conn(str(tmp_path / "test.db"))
    yield {
        "conn": conn,
        "user": UserRepo(conn),
        "pat": PatRepo(conn),
        "ws": WsContainerRepo(conn),
        "identity": IdentityRepo(conn),
    }
    conn.close()


# ---------------------------------------------------------------------------
# UserRepo
# ---------------------------------------------------------------------------


class TestUserRepo:
    def test_add_and_get_by_id(self, repos):
        u = repos["user"].add("mark", "Mark", "hash123")
        assert u.user_name == "mark"
        assert u.user_display_name == "Mark"
        assert u.password_hash == "hash123"
        assert u.openai_api_key is None

        fetched = repos["user"].get_by_id(u.user_id)
        assert fetched is not None
        assert fetched.user_name == "mark"

    def test_get_by_name(self, repos):
        repos["user"].add("alice", "Alice", "hash1")
        u = repos["user"].get_by_name("alice")
        assert u is not None
        assert u.user_display_name == "Alice"

    def test_get_by_name_not_found(self, repos):
        assert repos["user"].get_by_name("nonexistent") is None

    def test_list_all(self, repos):
        repos["user"].add("a", "A", "h1")
        repos["user"].add("b", "B", "h2")
        users = repos["user"].list_all()
        assert len(users) == 2

    def test_delete(self, repos):
        u = repos["user"].add("mark", "Mark", "hash")
        assert repos["user"].delete(u.user_id) is True
        assert repos["user"].get_by_id(u.user_id) is None

    def test_delete_not_found(self, repos):
        assert repos["user"].delete("nonexistent") is False


# ---------------------------------------------------------------------------
# PatRepo
# ---------------------------------------------------------------------------


class TestPatRepo:
    def test_add_and_list(self, repos):
        u = repos["user"].add("mark", "Mark", "hash")
        pat = repos["pat"].add(u.user_id, "abc123hash", "laptop")
        assert pat.label == "laptop"
        assert pat.user_id == u.user_id

        pats = repos["pat"].list_by_user(u.user_id)
        assert len(pats) == 1
        assert pats[0].label == "laptop"

    def test_delete(self, repos):
        u = repos["user"].add("mark", "Mark", "hash")
        pat = repos["pat"].add(u.user_id, "hash", "test")
        assert repos["pat"].delete(pat.id) is True
        assert repos["pat"].get_by_id(pat.id) is None

    def test_verify_found(self, repos):
        u = repos["user"].add("mark", "Mark", "hash")
        repos["pat"].add(u.user_id, "abchash", "test")
        pat = repos["pat"].verify("abchash")
        assert pat is not None

    def test_verify_not_found(self, repos):
        assert repos["pat"].verify("nonexistent") is None

    def test_verify_expired(self, repos):
        u = repos["user"].add("mark", "Mark", "hash")
        # Expired token
        repos["pat"].add(u.user_id, "expiredhash", "test", expires_at="2020-01-01T00:00:00Z")
        assert repos["pat"].verify("expiredhash") is None

    def test_touch_last_used(self, repos):
        u = repos["user"].add("mark", "Mark", "hash")
        pat = repos["pat"].add(u.user_id, "hash", "test")
        repos["pat"].touch_last_used(pat.id)
        updated = repos["pat"].get_by_id(pat.id)
        assert updated.last_used_at is not None


# ---------------------------------------------------------------------------
# WsContainerRepo
# ---------------------------------------------------------------------------


class TestWsContainerRepo:
    def test_add_and_get(self, repos):
        u = repos["user"].add("mark", "Mark", "hash")
        ws = repos["ws"].add(
            user_id=u.user_id,
            container_name="everlingo-mark-a1b2c3d4",
            host_workspace_dir="/ws/mark/a1b2c3d4",
            is_default=True,
        )
        assert ws.status == "absent"
        assert ws.is_default is True
        assert ws.docker_container_id is None

        fetched = repos["ws"].get_by_id(ws.ws_container_id)
        assert fetched is not None
        assert fetched.container_name == "everlingo-mark-a1b2c3d4"

    def test_get_default(self, repos):
        u = repos["user"].add("mark", "Mark", "hash")
        ws1 = repos["ws"].add(u.user_id, "everlingo-mark-a1b2c3d4", "/ws/mark/a", is_default=True)
        default = repos["ws"].get_default(u.user_id)
        assert default is not None
        assert default.ws_container_id == ws1.ws_container_id

    def test_set_default(self, repos):
        u = repos["user"].add("mark", "Mark", "hash")
        ws1 = repos["ws"].add(u.user_id, "everlingo-mark-a1b2c3d4", "/ws/mark/a", is_default=True)
        ws2 = repos["ws"].add(u.user_id, "everlingo-mark-e5f6g7h8", "/ws/mark/b", is_default=False)
        repos["ws"].set_default(ws2.ws_container_id, u.user_id)
        assert repos["ws"].get_default(u.user_id).ws_container_id == ws2.ws_container_id

    def test_update_status(self, repos):
        u = repos["user"].add("mark", "Mark", "hash")
        ws = repos["ws"].add(u.user_id, "everlingo-mark-a1b2c3d4", "/ws/mark/a", is_default=True)
        repos["ws"].update_status(ws.ws_container_id, "started", docker_container_id="abc123")
        updated = repos["ws"].get_by_id(ws.ws_container_id)
        assert updated.status == "started"
        assert updated.docker_container_id == "abc123"

    def test_list_by_user(self, repos):
        u = repos["user"].add("mark", "Mark", "hash")
        repos["ws"].add(u.user_id, "everlingo-mark-a", "/ws/mark/a", is_default=True)
        repos["ws"].add(u.user_id, "everlingo-mark-b", "/ws/mark/b", is_default=False)
        containers = repos["ws"].list_by_user(u.user_id)
        assert len(containers) == 2

    def test_list_by_status(self, repos):
        u = repos["user"].add("mark", "Mark", "hash")
        repos["ws"].add(u.user_id, "everlingo-mark-a", "/ws/mark/a", is_default=True)
        ws2 = repos["ws"].add(u.user_id, "everlingo-mark-b", "/ws/mark/b", is_default=False)
        repos["ws"].update_status(ws2.ws_container_id, "started")
        started = repos["ws"].list_by_status("started")
        assert len(started) == 1
        assert started[0].ws_container_id == ws2.ws_container_id

    def test_delete(self, repos):
        u = repos["user"].add("mark", "Mark", "hash")
        ws = repos["ws"].add(u.user_id, "everlingo-mark-a", "/ws/mark/a", is_default=True)
        assert repos["ws"].delete(ws.ws_container_id) is True
        assert repos["ws"].get_by_id(ws.ws_container_id) is None

    def test_count_by_user(self, repos):
        u = repos["user"].add("mark", "Mark", "hash")
        assert repos["ws"].count_by_user(u.user_id) == 0
        repos["ws"].add(u.user_id, "everlingo-mark-a", "/ws/mark/a", is_default=True)
        assert repos["ws"].count_by_user(u.user_id) == 1


# ---------------------------------------------------------------------------
# IdentityRepo
# ---------------------------------------------------------------------------


class TestIdentityRepo:
    def test_list_by_user(self, repos):
        u = repos["user"].add("mark", "Mark", "hash")
        repos["conn"].execute(
            "INSERT INTO user_identities (identity_id, user_id, provider, subject, created_at) "
            "VALUES ('i1', ?, 'google', 'sub123', '2026-01-01Z')",
            (u.user_id,),
        )
        repos["conn"].commit()
        identities = repos["identity"].list_by_user(u.user_id)
        assert len(identities) == 1
        assert identities[0].provider == "google"

    def test_unlink(self, repos):
        u = repos["user"].add("mark", "Mark", "hash")
        repos["conn"].execute(
            "INSERT INTO user_identities (identity_id, user_id, provider, subject, created_at) "
            "VALUES ('i1', ?, 'google', 'sub123', '2026-01-01Z')",
            (u.user_id,),
        )
        repos["conn"].commit()
        assert repos["identity"].unlink("i1") is True
        assert repos["identity"].unlink("nonexistent") is False