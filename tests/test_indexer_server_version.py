# ref: docs/impl-spec/worksplace/vault-version-control.md §5 — /version/* 端点
# 用 FastAPI TestClient 直接驱动；通过 TestClient 触发 lifespan（AppState.open/close），
# 验证 /version/status|commit|log 等端点在 Workspace 未配置 git_backup / 已配置两种情形。

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from everlingo import workspace
from everlingo.mem.vault.version import git
from everlingo.models import GitBackup
from everlingo.mem.vault.search.server import AppState, create_app


@pytest.fixture
def env_root(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    root = tmp_path / "memory"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def state(env_root: Path) -> AppState:
    return AppState(socket_path=env_root.parent / "indexer.sock", langs=[])


@pytest.fixture
def client(state: AppState):
    with TestClient(create_app(state)) as c:
        yield c


def _write(root: Path, name: str, content: str = "x") -> None:
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_version_status_initialized_after_open(env_root: Path, client):
    """lifespan open 会 init memory repo，/version/status 应反映。"""
    r = client.get("/version/status")
    assert r.status_code == 200
    data = r.json()
    assert data["initialized"] is True
    assert data["enabled"] is False
    assert data["remote_configured"] is False
    assert data["dirty"] is False
    assert data["has_commits"] is True  # initial commit


def test_version_status_reflects_dirty(env_root: Path, client):
    _write(env_root, "note.md", "hello")
    r = client.get("/version/status")
    assert r.json()["dirty"] is True


def test_version_commit_sync(env_root: Path, client):
    _write(env_root, "note.md", "trigger")
    r = client.post("/version/commit")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert git.has_commits(env_root)
    assert not git.is_dirty(env_root)


def test_version_log(env_root: Path, client):
    _write(env_root, "n1.md", "a")
    client.post("/version/commit")
    _write(env_root, "n2.md", "b")
    client.post("/version/commit")
    r = client.get("/version/log")
    assert r.status_code == 200
    commits = r.json()["commits"]
    assert len(commits) >= 3  # initial + 2 manual
    assert commits[0]["message"].startswith("chore(vault)")


def test_version_apply_config_reloads_committer(env_root: Path, client, monkeypatch):
    """apply-config 应把 committer 切换为最新配置（enabled=True → 定时器启动）。"""
    r = client.post("/version/apply-config")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_version_force_push_to_remote(env_root: Path, client):
    """force-push 端点：apply-config 配置 remote 后应真实 git push --force 到远端。"""
    import subprocess

    from everlingo.models import GitBackup
    from everlingo.setting import save_git_backup

    bare = env_root.parent / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
    _write(env_root, "note.md", "force push content")
    save_git_backup(GitBackup(enabled=True, remote_url=str(bare), branch="main"))
    assert client.post("/version/apply-config").status_code == 200

    r = client.post("/version/force-push")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    proc = git.run_git(bare, ["log", "--oneline"])
    assert len(proc.stdout.strip().splitlines()) >= 1


def test_version_test_without_remote(env_root: Path, client):
    """未配置 remote_url 时 test 应返回 ok=False 而非常规异常。"""
    r = client.post("/version/test")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert "remote_url" in data["message"]