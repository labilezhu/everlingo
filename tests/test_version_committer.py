# ref: docs/impl-spec/worksplace/vault-version-control.md §3 — Committer 测试
# 用 tmp_path + monkeypatch setting，验证 init/initial-commit/定时 commit/final commit。

from __future__ import annotations

import time
from pathlib import Path

import pytest

from everlingo.mem.vault.version import git
from everlingo.mem.vault.version.committer import Committer, ensure_snapshot
from everlingo.models import GitBackup


@pytest.fixture
def memory_root(tmp_path: Path) -> Path:
    return tmp_path / "memory"


def _write(root: Path, name: str, content: str = "x") -> Path:
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _fake_backup(monkeypatch, backup: GitBackup) -> None:
    monkeypatch.setattr(
        "everlingo.setting.load_git_backup", lambda: backup
    )
    monkeypatch.setattr("everlingo.setting.save_git_backup", lambda b: None)


def test_start_inits_repo_and_initial_commit(memory_root: Path, monkeypatch):
    _write(memory_root, "USER.md", "vault content")
    _fake_backup(monkeypatch, GitBackup())
    c = Committer(memory_root, tick_seconds=0.05)
    c.start()
    assert git.is_repo(memory_root)
    assert git.has_commits(memory_root)
    commits = git.log(memory_root, limit=10)
    assert commits[0].message == "chore(vault): snapshot-of-vault-at-init"
    c.stop()


def test_disabled_backup_only_initial_and_no_timer(memory_root: Path, monkeypatch):
    _write(memory_root, "a.md", "v1")
    _fake_backup(monkeypatch, GitBackup(enabled=False))
    c = Committer(memory_root, tick_seconds=0.02)
    c.start()
    assert git.has_commits(memory_root)
    # enabled=false：定时器不启动
    assert c.running is False
    assert len(git.log(memory_root, limit=100)) == 1
    c.stop()


def test_autocommit_on_dirty_matches_message(memory_root: Path, monkeypatch):
    _write(memory_root, "b.md", "x")
    _fake_backup(monkeypatch, GitBackup(enabled=True, commit_interval=1, push_interval=0))
    c = Committer(memory_root, tick_seconds=0.02)
    c.start()
    # initial commit 落盘；再写一个文件，等定时器 commit
    _write(memory_root, "c.md", "y")
    deadline = time.time() + 3.0
    while time.time() < deadline:
        commits = git.log(memory_root, limit=100)
        if len(commits) >= 2:
            break
        time.sleep(0.02)
    c.stop()
    commits = git.log(memory_root, limit=100)
    messages = [cm.message for cm in commits]
    assert any(m.startswith("chore(vault): auto-snapshot") for m in messages)
    assert not git.is_dirty(memory_root)


def test_final_commit_on_stop(memory_root: Path, monkeypatch):
    """stop() 时若工作区 dirty 应产出 final-snapshot commit。"""
    _write(memory_root, "d.md", "d1")
    _fake_backup(monkeypatch, GitBackup(enabled=True, commit_interval=999, push_interval=0))
    c = Committer(memory_root, tick_seconds=3600.0)
    c.start()
    _write(memory_root, "e.md", "e1")  # dirty（定时器休眠中，不会抢先 commit）
    c.stop()  # final commit 应捕获 e.md
    commits = git.log(memory_root, limit=100)
    assert commits[0].message == "chore(vault): final-snapshot"
    assert not git.is_dirty(memory_root)


def test_start_renames_legacy_branch_to_configured(memory_root: Path, monkeypatch):
    """已存在 repo 本地在 master（legacy init）→ start() 后强制统一为配置 branch main。"""
    import subprocess

    memory_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q", "--initial-branch=master", str(memory_root)],
        check=True,
    )
    subprocess.run(["git", "-C", str(memory_root), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(memory_root), "config", "user.email", "t@t"], check=True)
    _write(memory_root, "note.md", "legacy")
    subprocess.run(["git", "-C", str(memory_root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(memory_root), "commit", "-q", "-m", "legacy"], check=True)
    assert git.current_branch(memory_root) == "master"

    _fake_backup(monkeypatch, GitBackup(enabled=True, commit_interval=1, push_interval=0))
    c = Committer(memory_root, tick_seconds=3600.0)
    c.start()
    assert git.current_branch(memory_root) == "main"
    c.stop()


def test_ensure_snapshot_idempotent(memory_root: Path):
    _write(memory_root, "f.md", "f1")
    assert ensure_snapshot(memory_root) is True
    # clean 后再次调用不产 commit
    assert ensure_snapshot(memory_root) is False


def test_ensure_snapshot_without_git(monkeypatch, memory_root: Path):
    monkeypatch.setattr(git, "git_available", lambda: False)
    _write(memory_root, "g.md", "g1")
    assert ensure_snapshot(memory_root) is False


# ref: docs/ADR/20260810-vault-version-control.md — P3 配置热重载
# apply_config / reload_config：保存 everlingo.yaml 后无需重启即生效


def test_apply_config_starts_timer_when_enabled(memory_root: Path, monkeypatch):
    _fake_backup(monkeypatch, GitBackup(enabled=False))
    c = Committer(memory_root, tick_seconds=3600.0)
    c.start()
    assert not c.running
    _write(memory_root, "h.md", "h1")
    # 热启用：enabled=True → 定时器应启动并 init repo + initial commit
    c.apply_config(
        GitBackup(enabled=True, commit_interval=1, push_interval=0)
    )
    assert c.running is True
    assert git.is_repo(memory_root)
    assert git.has_commits(memory_root)
    c.stop()


def test_apply_config_stops_timer_when_disabled(memory_root: Path, monkeypatch):
    _fake_backup(monkeypatch, GitBackup(enabled=True, commit_interval=1, push_interval=0))
    c = Committer(memory_root, tick_seconds=3600.0)
    c.start()
    assert c.running is True
    c.apply_config(GitBackup(enabled=False))
    assert c.running is False
    c.stop()


def test_reload_config_reads_yaml_and_applies(memory_root: Path, monkeypatch):
    """reload_config 从 setting 重新读取（模拟 gateway 保存后调用）。"""
    state = {"backup": GitBackup(enabled=False)}

    def load():
        return state["backup"]

    monkeypatch.setattr("everlingo.setting.load_git_backup", load)
    monkeypatch.setattr("everlingo.setting.save_git_backup", lambda b: None)

    c = Committer(memory_root, tick_seconds=3600.0)
    c.start()
    assert not c.running
    # 外部改了 yaml → 热重载后定时器启动
    state["backup"] = GitBackup(enabled=True, commit_interval=1, push_interval=0)
    updated = c.reload_config()
    assert c.running is True
    assert updated.enabled is True
    c.stop()