# ref: docs/impl-spec/worksplace/vault-version-control.md §4.3 — restore 流程测试
# 用本地 bare repo 模拟远端，验证：无冲突成功 / 冲突打 backup 分支无覆盖 / hard reset。

from __future__ import annotations

import subprocess
from pathlib import Path

from everlingo.mem.vault.version import git
from everlingo.mem.vault.version.restore import (
    RestoreResult,
    hard_reset_to_remote,
    restore_vault,
)


def _bare(tmp_path: Path, name: str = "remote.git") -> Path:
    bare = tmp_path / name
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
    return bare


def _init_local(root: Path) -> None:
    git.init_repo(root)


def _write(root: Path, name: str, content: str) -> Path:
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _clone_push(bare: Path, tmp_path: Path, filename: str, content: str):
    """从远端 clone 一份、改一个文件、push 回远端（模拟异机提交）。"""
    clone = tmp_path / ("clone_" + filename)
    subprocess.run(["git", "clone", "-q", str(bare), str(clone)], check=True)
    (clone / filename).write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(clone), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(clone), "commit", "-q", "-m", f"remote {filename}"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(clone), "push", "origin", "main"], check=True
    )


def test_restore_success_no_conflict(tmp_path: Path):
    bare = _bare(tmp_path)
    root = tmp_path / "memory"
    _init_local(root)
    _write(root, "a.md", "a1")
    git.add_and_commit(root, "local a")
    git.ensure_remote(root, str(bare))
    git.push(root, remote="origin", branch="main")

    # 远端新增不同文件
    _clone_push(bare, tmp_path, "b.md", "b1")
    # 本地也改了不同文件
    _write(root, "c.md", "c1")
    git.add_and_commit(root, "local c")

    result = restore_vault(root, remote_url=str(bare), branch="main")
    assert result.ok is True
    assert result.backup_branch is None
    # c.md 与 b.md 都在
    assert (root / "b.md").read_text(encoding="utf-8") == "b1"
    assert (root / "c.md").read_text(encoding="utf-8") == "c1"


def test_restore_conflict_creates_backup_branch_without_overwrite(tmp_path: Path):
    bare = _bare(tmp_path)
    root = tmp_path / "memory"
    _init_local(root)
    _write(root, "same.md", "base")
    git.add_and_commit(root, "base")
    git.ensure_remote(root, str(bare))
    git.push(root, remote="origin", branch="main")

    _clone_push(bare, tmp_path, "same.md", "remote-version")
    _write(root, "same.md", "local-version")
    git.add_and_commit(root, "local same")

    result = restore_vault(root, remote_url=str(bare), branch="main")
    assert result.ok is False
    assert result.backup_branch is not None
    assert result.backup_branch.startswith("backup/restore-")
    assert "same.md" in result.conflicts
    # 工作区未被覆盖：仍是本地版本
    assert (root / "same.md").read_text(encoding="utf-8") == "local-version"


def test_restore_not_repo_returns_fail(tmp_path: Path):
    root = tmp_path / "memory"
    result = restore_vault(root, remote_url=str(tmp_path / "x.git"))
    assert result.ok is False
    assert "未初始化" in result.message


def test_restore_missing_repo_path(tmp_path: Path):
    """memory repo 不存在时 restore 返回失败而非异常。"""
    result = restore_vault(tmp_path / "no-such", remote_url="")
    assert result.ok is False


def test_hard_reset_to_remote(tmp_path: Path):
    bare = _bare(tmp_path)
    root = tmp_path / "memory"
    _init_local(root)
    _write(root, "f.md", "v1")
    git.add_and_commit(root, "v1")
    git.ensure_remote(root, str(bare))
    git.push(root, remote="origin", branch="main")

    _clone_push(bare, tmp_path, "f.md", "remote-new")
    # 本地又写了一个未推到远端的分支内容
    _write(root, "local.md", "local")

    assert hard_reset_to_remote(root, remote_url=str(bare), branch="main") is True
    # 已被远端覆盖：remote-new 生效，local.md 消失
    assert (root / "f.md").read_text(encoding="utf-8") == "remote-new"
    assert not (root / "local.md").exists()