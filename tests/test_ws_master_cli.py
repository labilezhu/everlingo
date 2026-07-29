"""WS-Master CLI 测试：子命令覆盖。

使用临时 sqlite 文件，mock 掉 config 和 db 调用。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from everlingo.ws_master.cli import (
    _hash_password,
    _check_password,
    _new_short_id,
    dispatch,
)
from everlingo.ws_master.config import MasterConfig
from everlingo.ws_master.db import get_conn
from everlingo.ws_master.repo import PatRepo, UserRepo, WsContainerRepo


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


class TestPasswordHashing:
    def test_hash_and_verify(self):
        pw = "my-secret-password"
        hashed = _hash_password(pw)
        assert _check_password(pw, hashed) is True

    def test_wrong_password(self):
        hashed = _hash_password("correct")
        assert _check_password("wrong", hashed) is False

    def test_invalid_hash_format(self):
        assert _check_password("x", "invalid-hash") is False


# ---------------------------------------------------------------------------
# Helper: build args namespace for CLI dispatch
# ---------------------------------------------------------------------------


def _make_args(config_path: str, **kwargs) -> argparse.Namespace:
    return argparse.Namespace(config=config_path, **kwargs)


# ---------------------------------------------------------------------------
# User CLI
# ---------------------------------------------------------------------------


class TestUserCli:
    def test_user_add(self, tmp_path: Path):
        config_path = _write_config(tmp_path, "test.db")
        args = _make_args(
            config_path,
            ws_master_cmd="user",
            user_cmd="add",
            name="mark",
            display_name="Mark",
            password="secret123",
        )
        rc = dispatch(args)
        assert rc == 0

        # Verify in DB
        conn = get_conn(str(tmp_path / "test.db"))
        user_repo = UserRepo(conn)
        ws_repo = WsContainerRepo(conn)
        user = user_repo.get_by_name("mark")
        assert user is not None
        assert user.user_display_name == "Mark"
        # Default ws should exist
        ws_list = ws_repo.list_by_user(user.user_id)
        assert len(ws_list) == 1
        assert ws_list[0].status == "absent"
        assert ws_list[0].is_default is True
        conn.close()

    def test_user_add_duplicate(self, tmp_path: Path):
        config_path = _write_config(tmp_path, "test.db")
        # First add
        dispatch(_make_args(config_path, ws_master_cmd="user", user_cmd="add", name="mark", display_name="Mark", password="pw"))
        # Second add - should fail
        args = _make_args(config_path, ws_master_cmd="user", user_cmd="add", name="mark", display_name="Mark", password="pw")
        rc = dispatch(args)
        assert rc == 1

    def test_user_list(self, tmp_path: Path):
        config_path = _write_config(tmp_path, "test.db")
        dispatch(_make_args(config_path, ws_master_cmd="user", user_cmd="add", name="mark", display_name="Mark", password="pw"))
        args = _make_args(config_path, ws_master_cmd="user", user_cmd="list")
        rc = dispatch(args)
        assert rc == 0

    def test_user_rm(self, tmp_path: Path):
        config_path = _write_config(tmp_path, "test.db")
        dispatch(_make_args(config_path, ws_master_cmd="user", user_cmd="add", name="mark", display_name="Mark", password="pw"))
        args = _make_args(config_path, ws_master_cmd="user", user_cmd="rm", name="mark", purge=False)
        rc = dispatch(args)
        assert rc == 0
        # Verify
        conn = get_conn(str(tmp_path / "test.db"))
        user_repo = UserRepo(conn)
        assert user_repo.get_by_name("mark") is None
        conn.close()

    def test_user_rm_not_found(self, tmp_path: Path):
        config_path = _write_config(tmp_path, "test.db")
        args = _make_args(config_path, ws_master_cmd="user", user_cmd="rm", name="nonexistent", purge=False)
        rc = dispatch(args)
        assert rc == 1


# ---------------------------------------------------------------------------
# PAT CLI
# ---------------------------------------------------------------------------


class TestPatCli:
    def test_pat_add(self, tmp_path: Path):
        config_path = _write_config(tmp_path, "test.db")
        dispatch(_make_args(config_path, ws_master_cmd="user", user_cmd="add", name="mark", display_name="Mark", password="pw"))
        args = _make_args(config_path, ws_master_cmd="pat", pat_cmd="add", user="mark", label="laptop", expires=None)
        rc = dispatch(args)
        assert rc == 0

    def test_pat_list(self, tmp_path: Path):
        config_path = _write_config(tmp_path, "test.db")
        dispatch(_make_args(config_path, ws_master_cmd="user", user_cmd="add", name="mark", display_name="Mark", password="pw"))
        dispatch(_make_args(config_path, ws_master_cmd="pat", pat_cmd="add", user="mark", label="laptop", expires=None))
        args = _make_args(config_path, ws_master_cmd="pat", pat_cmd="list", user="mark")
        rc = dispatch(args)
        assert rc == 0

    def test_pat_rm(self, tmp_path: Path):
        config_path = _write_config(tmp_path, "test.db")
        dispatch(_make_args(config_path, ws_master_cmd="user", user_cmd="add", name="mark", display_name="Mark", password="pw"))
        # Add PAT and capture its ID
        conn = get_conn(str(tmp_path / "test.db"))
        user_repo = UserRepo(conn)
        pat_repo = PatRepo(conn)
        user = user_repo.get_by_name("mark")
        from everlingo.ws_master.pat_utils import generate_pat
        plain, hashed = generate_pat()
        pat = pat_repo.add(user.user_id, hashed, "laptop")
        pat_id = pat.id
        conn.close()

        args = _make_args(config_path, ws_master_cmd="pat", pat_cmd="rm", pat_id=pat_id)
        rc = dispatch(args)
        assert rc == 0
        # Verify by re-opening connection
        conn2 = get_conn(str(tmp_path / "test.db"))
        pat_repo2 = PatRepo(conn2)
        assert pat_repo2.get_by_id(pat_id) is None
        conn2.close()


# ---------------------------------------------------------------------------
# WS CLI
# ---------------------------------------------------------------------------


class TestWsCli:
    def test_ws_add(self, tmp_path: Path):
        config_path = _write_config(tmp_path, "test.db")
        dispatch(_make_args(config_path, ws_master_cmd="user", user_cmd="add", name="mark", display_name="Mark", password="pw"))
        # user add already created a default ws, so we need to add another
        # But max_ws_per_user=1, so this should fail
        args = _make_args(config_path, ws_master_cmd="ws", ws_cmd="add", user="mark")
        rc = dispatch(args)
        assert rc == 1  # max_ws_per_user exceeded

    def test_ws_list(self, tmp_path: Path):
        config_path = _write_config(tmp_path, "test.db")
        dispatch(_make_args(config_path, ws_master_cmd="user", user_cmd="add", name="mark", display_name="Mark", password="pw"))
        args = _make_args(config_path, ws_master_cmd="ws", ws_cmd="list", user="mark")
        rc = dispatch(args)
        assert rc == 0

    def test_ws_set_default(self, tmp_path: Path):
        config_path = _write_config(tmp_path, "test.db")
        dispatch(_make_args(config_path, ws_master_cmd="user", user_cmd="add", name="mark", display_name="Mark", password="pw"))
        # Get the ws id
        conn = get_conn(str(tmp_path / "test.db"))
        ws_repo = WsContainerRepo(conn)
        user_repo = UserRepo(conn)
        user = user_repo.get_by_name("mark")
        ws_list = ws_repo.list_by_user(user.user_id)
        conn.close()

        args = _make_args(config_path, ws_master_cmd="ws", ws_cmd="set-default", ws_id=ws_list[0].ws_container_id)
        rc = dispatch(args)
        assert rc == 0

    def test_ws_rm_not_found(self, tmp_path: Path):
        config_path = _write_config(tmp_path, "test.db")
        args = _make_args(config_path, ws_master_cmd="ws", ws_cmd="rm", ws_id="nonexistent", purge=False)
        rc = dispatch(args)
        assert rc == 1


# ---------------------------------------------------------------------------
# Identity CLI
# ---------------------------------------------------------------------------


class TestIdentityCli:
    def test_identity_list(self, tmp_path: Path):
        config_path = _write_config(tmp_path, "test.db")
        dispatch(_make_args(config_path, ws_master_cmd="user", user_cmd="add", name="mark", display_name="Mark", password="pw"))
        args = _make_args(config_path, ws_master_cmd="identity", identity_cmd="list", user="mark")
        rc = dispatch(args)
        assert rc == 0

    def test_identity_unlink_not_found(self, tmp_path: Path):
        config_path = _write_config(tmp_path, "test.db")
        args = _make_args(config_path, ws_master_cmd="identity", identity_cmd="unlink", identity_id="nonexistent")
        rc = dispatch(args)
        assert rc == 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_config(tmp_path: Path, db_name: str) -> str:
    """Write a minimal ws_master.yaml and return its path."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "ws_master.yaml"
    config_path.write_text(
        f"master:\n"
        f"  listen: 0.0.0.0:8101\n"
        f"  shared_secret: test-secret\n"
        f"  db: {tmp_path / db_name}\n"
        f"  host_ws_dir: {tmp_path / 'workspaces'}\n"
        f"  container_ws_dir: /workspaces\n"
        f"  image: test-image:latest\n"
        f"  network: test-net\n"
        f"  ws_template: /dev/null\n"
        f"  openai_api_key: test-key\n"
        f"  openai_base_url: https://test.api\n"
        f"  openai_model: test-model\n"
        f"  openai_embedding_model: test-embed\n"
        f"  idle_timeout: 1200\n"
        f"  healthcheck_interval: 60\n"
        f"  readiness_timeout: 60\n"
        f"  max_ws_per_user: 1\n"
    )
    return str(config_path)