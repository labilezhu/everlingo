# ref: docs/impl-spec/worksplace/vault-version-control.md §4.3 — restore 恢复流程
#   1. commit(memory_root, "chore(vault): pre-restore snapshot")   # 捕获本地改动
#   2. fetch(memory_root, remote)
#   3. ok, conflicts = rebase(memory_root, f"{remote}/{branch}")
#   4. ok → success；否则把当前 HEAD 打 backup 分支，返回 conflicts（由用户决定 hard reset）。

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from everlingo.i18n.version import version_t

from . import git

logger = logging.getLogger(__name__)


@dataclass
class RestoreResult:
    ok: bool
    backup_branch: str | None = None
    conflicts: list[str] | None = None
    message: str = ""


def restore_vault(
    memory_root: Path,
    *,
    remote_url: str,
    branch: str = "main",
    env: dict[str, str] | None = None,
    config: dict[str, str] | None = None,
    interface_language: str | None = None,
) -> RestoreResult:
    """从远端恢复（commit → fetch → rebase）。

    冲突时不自动覆盖工作区：创建 `backup/pre-restore-<ts>` 分支托底，
    由调用方（CLI /console）在用户确认后 hard reset。
    """
    root = Path(memory_root)
    if not git.git_available() or not git.is_repo(root):
        return RestoreResult(
            ok=False, message=version_t("repo_not_initialized", interface_language)
        )

    # 1. 捕获本地改动
    try:
        git.add_and_commit(
            root,
            "chore(vault): pre-restore snapshot",
            interface_language=interface_language,
        )
    except git.GitError as e:
        return RestoreResult(
            ok=False,
            message=version_t("pre_restore_commit_failed", interface_language, error=str(e)),
        )

    # 2. fetch
    try:
        git.ensure_remote(root, remote_url, interface_language=interface_language)
        git.fetch(
            root,
            env=env,
            config=config,
            interface_language=interface_language,
        )
    except git.GitError as e:
        return RestoreResult(
            ok=False,
            message=version_t("fetch_failed", interface_language, error=str(e)),
        )

    # 3. rebase 到远端
    ok, conflicts = git.rebase(root, f"origin/{branch}")
    if ok:
        return RestoreResult(ok=True, message=version_t("rebased_to_remote", interface_language))

    # 4. 冲突 → 备份分支（不覆盖工作区），交由用户决定 hard reset
    try:
        backup = git.checkout_to_backup_branch(
            root, "HEAD", interface_language=interface_language
        )
    except git.GitError:
        backup = None
    return RestoreResult(
        ok=False,
        backup_branch=backup,
        conflicts=conflicts,
        message=version_t("conflict_saved_to_backup", interface_language),
    )


def hard_reset_to_remote(
    memory_root: Path,
    *,
    remote_url: str,
    branch: str = "main",
    env: dict[str, str] | None = None,
    config: dict[str, str] | None = None,
    interface_language: str | None = None,
) -> bool:
    """commit → fetch → git reset --hard origin/<branch>（用户确认后调用）。"""
    root = Path(memory_root)
    if not git.git_available() or not git.is_repo(root):
        return False
    try:
        git.add_and_commit(
            root,
            "chore(vault): pre-restore snapshot",
            interface_language=interface_language,
        )
        git.ensure_remote(root, remote_url, interface_language=interface_language)
        git.fetch(
            root,
            env=env,
            config=config,
            interface_language=interface_language,
        )
        git.hard_reset(root, "origin", branch, interface_language=interface_language)
        return True
    except git.GitError as e:
        logger.warning("hard reset 失败: %s", e)
        return False