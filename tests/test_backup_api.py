# ref: docs/ADR/20260810-vault-version-control.md — P3/P4 gateway REST API
# /api/backup/* 路由测试：mock SearchClient（UDS 网络）与真实 setting 落盘（yaml）。
# 覆盖：状态、配置读写（ssh/https_pat/https_none）、pat 掩码与 pat_changed 语义、
# 各操作端点、indexer 不可达降级。

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from everlingo import workspace
from everlingo.gateway import backup_api
from everlingo.gateway.web_acceptor import app
from everlingo.mem.vault.search.protocol import (
    RestoreResponse,
    VersionLogResponse,
    VersionStatusResponse,
    VersionTestResponse,
)

_fake_client: MagicMock | None = None


@pytest.fixture(autouse=True)
def ws(tmp_path: Path, monkeypatch) -> None:
    """初始化 workspace 指向 tmp（setting.yaml 落盘路径）。

    用 monkeypatch 改 _current_ws_dir 而非 init_workspace_dir()：后者直接改
    进程级全局，测试后不还原，会污染后续 test 文件（如 test_setting.py）。
    """
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)


@pytest.fixture(autouse=True)
def fake_indexer(monkeypatch):
    """替换 backup_api._get_client 为可控 Mock（模拟 indexer 的 /version/*）。"""
    global _fake_client
    client = MagicMock()

    def _get():
        return client

    monkeypatch.setattr(backup_api, "_get_client", _get)
    # 清全局缓存，避免真实 SearchClient 复用
    backup_api._client = None
    _fake_client = client
    yield client
    backup_api._client = None


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _status_response() -> VersionStatusResponse:
    return VersionStatusResponse(
        enabled=True,
        initialized=True,
        dirty=False,
        has_commits=True,
        last_commit_at="2026-08-11T10:00:00+00:00",
        last_push_at=None,
        remote_configured=True,
        ahead=1,
        behind=0,
        branch="main",
        remote_url="git@github.com:user/vault.git",
    )


class TestStatus:
    def test_returns_aggregated_status(self, client, fake_indexer):
        fake_indexer.version_status.return_value = _status_response()
        r = client.get("/api/backup/status")
        assert r.status_code == 200
        data = r.json()
        assert data["enabled"] is True
        assert data["remote_url"] == "git@github.com:user/vault.git"
        assert data["ahead"] == 1

    def test_indexer_unreachable_returns_503(self, client, fake_indexer):
        fake_indexer.version_status.return_value = None
        r = client.get("/api/backup/status")
        assert r.status_code == 503


class TestConfig:
    def test_get_returns_masked_pat(self, client):
        # 预置配置含 pat → GET 应返回掩码（末 4 位）
        from everlingo.models import GitBackup, GitBackupAuth
        from everlingo.setting import save_git_backup

        save_git_backup(
            GitBackup(
                enabled=True,
                remote_url="https://github.com/user/vault.git",
                auth=GitBackupAuth(method="https_pat", pat="github_pat_secret"),
            )
        )
        r = client.get("/api/backup/config")
        assert r.status_code == 200
        data = r.json()
        assert data["auth"]["pat"] == backup_api.mask_pat("github_pat_secret")
        assert data["auth"]["pat"].endswith("cret")
        assert "*" in data["auth"]["pat"]
        assert data["remote_url"] == "https://github.com/user/vault.git"

    def test_get_masks_short_pat(self, client):
        from everlingo.models import GitBackup, GitBackupAuth
        from everlingo.setting import save_git_backup

        save_git_backup(GitBackup(auth=GitBackupAuth(method="https_pat", pat="ab")))
        r = client.get("/api/backup/config")
        assert r.json()["auth"]["pat"] == "**"

    def test_post_saves_and_reloads(self, client, fake_indexer):
        fake_indexer.version_apply_config.return_value = True
        r = client.post(
            "/api/backup/config",
            json={
                "enabled": True,
                "remote_url": "git@github.com:user/vault.git",
                "branch": "main",
                "method": "ssh",
                "ssh_private_key_file": "/run/secrets/key",
                "push_interval": 0,
            },
        )
        assert r.status_code == 200
        fake_indexer.version_apply_config.assert_called_once()
        data = r.json()
        assert data["enabled"] is True
        assert data["auth"]["method"] == "ssh"
        # 落盘可读回
        from everlingo.setting import load_git_backup

        saved = load_git_backup()
        assert saved.remote_url == "git@github.com:user/vault.git"
        assert saved.auth.ssh_private_key_file == "/run/secrets/key"

    def test_post_accepts_https_pat(self, client, fake_indexer):
        fake_indexer.version_apply_config.return_value = True
        r = client.post(
            "/api/backup/config",
            json={
                "enabled": True,
                "remote_url": "https://github.com/user/vault.git",
                "branch": "main",
                "method": "https_pat",
                "pat": "github_pat_new",
                "pat_changed": True,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["auth"]["method"] == "https_pat"
        assert data["auth"]["pat"].endswith("_new")
        from everlingo.setting import load_git_backup

        saved = load_git_backup()
        assert saved.auth.method == "https_pat"
        assert saved.auth.pat == "github_pat_new"

    def test_post_rejects_unknown_method(self, client):
        r = client.post(
            "/api/backup/config",
            json={"enabled": True, "remote_url": "x", "method": "https_pat2"},
        )
        assert r.status_code == 400

    def test_post_preserves_existing_pat(self, client, fake_indexer):
        # 切到 ssh 且未提交 pat → 不清掉既有 pat（防覆盖 CLI 侧配置）
        from everlingo.models import GitBackup, GitBackupAuth
        from everlingo.setting import save_git_backup

        save_git_backup(
            GitBackup(
                remote_url="https://github.com/user/vault.git",
                auth=GitBackupAuth(method="https_pat", pat="github_pat_secret"),
            )
        )
        fake_indexer.version_apply_config.return_value = True
        r = client.post(
            "/api/backup/config",
            json={"enabled": False, "remote_url": "git@x:y.git", "method": "ssh"},
        )
        assert r.status_code == 200
        from everlingo.setting import load_git_backup

        saved = load_git_backup()
        assert saved.auth.pat == "github_pat_secret"

    def test_post_preserves_pat_when_not_changed(self, client, fake_indexer):
        # 提交 pat 但 pat_changed=false（掩码回传）→ 保留原值
        from everlingo.models import GitBackup, GitBackupAuth
        from everlingo.setting import save_git_backup

        save_git_backup(
            GitBackup(
                remote_url="https://github.com/user/vault.git",
                auth=GitBackupAuth(method="https_pat", pat="github_pat_secret"),
            )
        )
        fake_indexer.version_apply_config.return_value = True
        r = client.post(
            "/api/backup/config",
            json={
                "enabled": True,
                "remote_url": "https://github.com/user/vault.git",
                "method": "https_pat",
                "pat": backup_api.mask_pat("github_pat_secret"),
                "pat_changed": False,
            },
        )
        assert r.status_code == 200
        from everlingo.setting import load_git_backup

        assert load_git_backup().auth.pat == "github_pat_secret"

    def test_post_clears_pat_when_changed_empty(self, client, fake_indexer):
        from everlingo.models import GitBackup, GitBackupAuth
        from everlingo.setting import save_git_backup

        save_git_backup(
            GitBackup(auth=GitBackupAuth(method="https_pat", pat="github_pat_secret"))
        )
        fake_indexer.version_apply_config.return_value = True
        r = client.post(
            "/api/backup/config",
            json={
                "enabled": True,
                "remote_url": "https://github.com/user/vault.git",
                "method": "https_pat",
                "pat": "",
                "pat_changed": True,
            },
        )
        assert r.status_code == 200
        from everlingo.setting import load_git_backup

        assert load_git_backup().auth.pat == ""

    def test_mask_pat(self):
        assert backup_api.mask_pat("") == ""
        assert backup_api.mask_pat("ab") == "**"
        assert backup_api.mask_pat("abcdef") == "**cdef"
        assert backup_api.mask_pat("github_pat_secret").endswith("cret")
        assert "*" in backup_api.mask_pat("github_pat_secret")


class TestActions:
    def test_snapshot(self, client, fake_indexer):
        fake_indexer.version_commit.return_value = True
        r = client.post("/api/backup/snapshot")
        assert r.json() == {"ok": True}

    def test_push_unreachable(self, client, fake_indexer):
        fake_indexer.version_push.return_value = None
        r = client.post("/api/backup/push")
        assert r.status_code == 503

    def test_force_push(self, client, fake_indexer):
        fake_indexer.version_force_push.return_value = True
        r = client.post("/api/backup/force-push")
        assert r.status_code == 200
        assert r.json() == {"ok": True}

    def test_force_push_unreachable(self, client, fake_indexer):
        fake_indexer.version_force_push.return_value = None
        r = client.post("/api/backup/force-push")
        assert r.status_code == 503

    def test_pull(self, client, fake_indexer):
        fake_indexer.version_pull.return_value = RestoreResponse(
            ok=False,
            backup_branch="backup/restore-20260811-100000",
            conflicts=["memory/USER.md"],
            message="conflict",
        )
        r = client.post("/api/backup/pull")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        assert data["conflicts"] == ["memory/USER.md"]

    def test_test_remote(self, client, fake_indexer):
        fake_indexer.version_test_remote.return_value = VersionTestResponse(
            ok=True, message="远端可达，检测到 2 个分支头"
        )
        r = client.post("/api/backup/test")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_reset_hard(self, client, fake_indexer):
        fake_indexer.version_reset_hard.return_value = RestoreResponse(
            ok=True, message="hard reset 完成"
        )
        r = client.post("/api/backup/reset-hard")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_log(self, client, fake_indexer):
        fake_indexer.version_log.return_value = VersionLogResponse(commits=[])
        r = client.get("/api/backup/log?limit=5")
        assert r.status_code == 200
        assert r.json()["commits"] == []

    def test_restore(self, client, fake_indexer):
        fake_indexer.version_restore.return_value = RestoreResponse(
            ok=True, backup_branch="backup/restore-20260811-100000", message="ok"
        )
        r = client.post("/api/backup/restore", json={"commit_hash": "abc123"})
        assert r.status_code == 200
        fake_indexer.version_restore.assert_called_once_with("abc123")
        assert r.json()["backup_branch"].startswith("backup/restore-")