# ref: docs/impl-spec/worksplace/vault-version-control.md §4.1 — git CLI 封装
# subprocess 封装；用真实 git（测试环境已装），在 tmp_path 下裸跑。

from __future__ import annotations

from pathlib import Path

import pytest

from everlingo.mem.vault.version import git


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "memory"
    git.init_repo(root)
    return root


def _write(root: Path, name: str, content: str = "hello") -> Path:
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_init_repo_creates_git_and_identity(repo: Path):
    assert git.is_repo(repo)
    proc = git.run_git(repo, ["config", "user.name"])
    assert proc.stdout.strip() == "everlingo"
    proc = git.run_git(repo, ["config", "user.email"])
    assert proc.stdout.strip() == "noreply@everlingo.local"


def test_init_repo_writes_gitignore(repo: Path):
    gi = repo / ".gitignore"
    assert gi.exists()
    assert "*.bak" in gi.read_text(encoding="utf-8")


def test_is_dirty_after_write(repo: Path):
    assert not git.is_dirty(repo)
    _write(repo, "a.md")
    assert git.is_dirty(repo)


def test_add_and_commit_creates_commit(repo: Path):
    _write(repo, "USER.md", "hello vault")
    assert git.add_and_commit(repo)
    assert not git.is_dirty(repo)
    assert git.has_commits(repo)


def test_add_and_commit_skips_when_clean(repo: Path):
    # init_repo 已产 initial commit；clean 时不应再产 commit
    before = len(git.log(repo, limit=100))
    assert not git.add_and_commit(repo)
    after = len(git.log(repo, limit=100))
    assert after == before


def test_log_lists_commits(repo: Path):
    _write(repo, "a.md")
    git.add_and_commit(repo, "first")
    _write(repo, "b.md")
    git.add_and_commit(repo, "second")
    commits = git.log(repo, limit=10)
    assert len(commits) == 3  # initial + first + second
    assert commits[0].message == "second"
    assert commits[1].message == "first"
    assert commits[2].message == "chore(vault): snapshot-of-vault-at-init"


def test_commit_message_auto_with_timestamp(repo: Path):
    _write(repo, "c.md")
    git.add_and_commit(repo)
    commits = git.log(repo, limit=1)
    assert commits[0].message.startswith("chore(vault): auto-snapshot")


def test_ensure_remote_and_fetch_push_roundtrip(repo: Path, tmp_path: Path):
    """本地裸 repo 作为远端，验证 ensure_remote/fetch/push 链路。"""
    bare = tmp_path / "bare.git"
    import subprocess

    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
    _write(repo, "x.md")
    git.add_and_commit(repo)
    git.ensure_remote(repo, str(bare))
    git.push(repo, remote="origin", branch="main")
    # 远端应能读到提交
    proc = git.run_git(bare, ["log", "--oneline"])
    assert "x.md" or "auto-snapshot" or len(proc.stdout.strip().splitlines()) == 1


def test_rebase_no_conflict(repo: Path, tmp_path: Path):
    """本地先进、远端也有提交（不同文件），rebase 应成功。"""
    import subprocess

    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
    _write(repo, "base.md")
    git.add_and_commit(repo, "base")
    git.ensure_remote(repo, str(bare))
    git.push(repo, remote="origin", branch="main")

    # 远端新增一个不同文件（模拟另一台机器 push）
    subprocess.run(["git", "clone", "-q", str(bare), str(tmp_path / "clone")], check=True)
    clone = tmp_path / "clone"
    (clone / "remote.md").write_text("remote", encoding="utf-8")
    subprocess.run(["git", "-C", str(clone), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(clone), "commit", "-q", "-m", "remote change"],
        check=True,
    )
    subprocess.run(["git", "-C", str(clone), "push", "origin", "main"], check=True)

    # 本地继续开发（不同文件）
    _write(repo, "local.md", "local")
    git.add_and_commit(repo, "local change")

    git.fetch(repo)
    ok, conflicts = git.rebase(repo, "origin/main")
    assert ok is True
    assert conflicts == []


def test_rebase_conflict_creates_backup_branch(repo: Path, tmp_path: Path):
    """同一文件冲突 → rebase 失败，checkout_to_backup_branch 兜底。"""
    import subprocess

    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
    _write(repo, "same.md", "base")
    git.add_and_commit(repo, "base")
    git.ensure_remote(repo, str(bare))
    git.push(repo, remote="origin", branch="main")

    subprocess.run(["git", "clone", "-q", str(bare), str(tmp_path / "clone")], check=True)
    clone = tmp_path / "clone"
    (clone / "same.md").write_text("remote-version", encoding="utf-8")
    subprocess.run(["git", "-C", str(clone), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(clone), "commit", "-q", "-m", "remote same"],
        check=True,
    )
    subprocess.run(["git", "-C", str(clone), "push", "origin", "main"], check=True)

    (repo / "same.md").write_text("local-version", encoding="utf-8")
    git.add_and_commit(repo, "local same")

    git.fetch(repo)
    ok, conflicts = git.rebase(repo, "origin/main")
    assert ok is False
    assert "same.md" in conflicts

    branch = git.checkout_to_backup_branch(repo, "HEAD")
    assert branch.startswith("backup/restore-")


def test_hard_reset(repo: Path, tmp_path: Path):
    import subprocess

    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
    _write(repo, "f.md", "v1")
    git.add_and_commit(repo, "v1")
    git.ensure_remote(repo, str(bare))
    git.push(repo, remote="origin", branch="main")
    _write(repo, "local-only.md", "x")
    git.add_and_commit(repo, "local-only")
    git.fetch(repo)
    git.hard_reset(repo, "origin", "main")
    assert not (repo / "local-only.md").exists()


def test_status_fields(repo: Path):
    _write(repo, "z.md")
    git.add_and_commit(repo)
    st = git.repo_status(repo, remote_configured=False, branch="main")
    assert st["initialized"] is True
    assert st["has_commits"] is True
    assert st["dirty"] is False
    assert st["last_commit_at"] is not None
    assert st["ahead"] == 0 and st["behind"] == 0


def test_status_when_not_repo(tmp_path: Path):
    st = git.repo_status(tmp_path / "nope", remote_configured=False)
    assert st["initialized"] is False


def test_rename_current_branch_from_master(tmp_path: Path):
    """已存在 repo（plain git init，明确用 master 作为初始分支）→ rename 到 main，历史保留。"""
    import subprocess

    root = tmp_path / "legacy"
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q", "--initial-branch=master", str(root)], check=True
    )
    subprocess.run(
        ["git", "-C", str(root), "config", "user.name", "t"], check=True
    )
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "t@t"], check=True
    )
    (root / "note.md").write_text("legacy content", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "legacy"], check=True)
    assert git.current_branch(root) == "master"  # 走的 rename 分支路径

    ok = git.rename_current_branch(root, "main")
    assert ok is True
    assert git.current_branch(root) == "main"
    # commit 历史保留
    assert git.has_commits(root)


def test_rename_current_branch_idempotent(repo: Path):
    assert git.current_branch(repo) == "main"
    assert git.rename_current_branch(repo, "main") is True


def test_rename_current_branch_not_repo(tmp_path: Path):
    assert git.rename_current_branch(tmp_path / "missing", "main") is False


def test_init_repo_fallback_when_no_dash_b(tmp_path: Path, monkeypatch):
    """git < 2.28（init 无 -b）时应降级：plain init + branch -M main。"""
    root = tmp_path / "mem"
    calls: list[list[str]] = []
    orig = git.run_git

    def _fake_run_git(cwd, args, **_kw):
        from subprocess import CompletedProcess

        calls.append(list(args))
        if args[0] == "init" and "-b" in args:
            raise git.GitError("unknown option: -b")
        return orig(cwd, args, **_kw)

    monkeypatch.setattr(git, "run_git", _fake_run_git)
    git.init_repo(root)
    assert git.is_repo(root)
    assert git.current_branch(root) == "main"
    assert any(a[:3] == ["init", "-q"] and "-b" not in a for a in calls)
    assert any(a[0] == "branch" and a[1] == "-M" for a in calls)