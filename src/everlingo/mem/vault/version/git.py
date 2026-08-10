# ref: docs/impl-spec/worksplace/vault-version-control.md §2/§4 — git repo 管理与操作封装
# subprocess 封装 git CLI。全部调用固定带 `-c safe.directory=<repo_root>`（规避挂载
# workspace 的 host UID ≠ 容器内 euid 的 `detected dubious ownership` 拒绝），并置
# GIT_CONFIG_GLOBAL=/dev/null + GIT_CONFIG_SYSTEM=/dev/null（不依赖容器内会丢失的全局
# config；repo-local config 仍生效，见 §11.2/§11.5）。

from __future__ import annotations

import datetime
import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

logger = logging.getLogger(__name__)

GIT_IDENTITY_NAME = "everlingo"
GIT_IDENTITY_EMAIL = "noreply@everlingo.local"

# $workspace/memory/.gitignore 落盘内容（见 vault-version-control.md §2.2）
GITIGNORE_CONTENT = """\
# 语言索引 DB（程序派生，可 reindex --rebuild 重建）
languages/*/index/

# 程序内部临时文件（无用户数据价值，watcher 不索引）
**/vault/tmp/

# 历史遗留备份（USER.md.bak 机制已停）
*.bak
"""

_GIT_DEFAULT_TIMEOUT = 120.0


class GitError(RuntimeError):
    """git 命令失败（returncode != 0 / 未安装 / 超时）。"""

    def __init__(self, message: str, returncode: int = 0, stderr: str = "") -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


@dataclass
class GitCommit:
    """git log 中的一条提交。"""

    hash: str
    time: str
    message: str


def git_available() -> bool:
    """探测 git CLI 是否存在（不影响主流程）。"""
    try:
        proc = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=10.0,
        )
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("HOME", str(Path.home()))
    # 忽略全局/系统 config：我们的 repo 配置全部走 repo-local 或命令行 -c。
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    return env


def run_git(
    cwd: Path,
    args: list[str],
    *,
    check: bool = True,
    config: Mapping[str, str] | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = _GIT_DEFAULT_TIMEOUT,
) -> subprocess.CompletedProcess[str]:
    """执行 git 命令。

    :param cwd:   repo 根目录（$workspace/memory）。
    :param args:  git 子命令参数（如 ["status", "--porcelain"]）。
    :param check: True 时 returncode!=0 抛 GitError。
    :param config: 附加 `-c key=value` 配置项（如 https_pat 的 http.extraheader）。
    :param env:   附加环境变量（如 ssh 的 GIT_SSH_COMMAND）。
    """
    full_env = _git_env()
    if env:
        full_env.update(env)
    cmd = ["git", "-c", f"safe.directory={cwd}"]
    for key, value in (config or {}).items():
        cmd += ["-c", f"{key}={value}"]
    cmd += list(args)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=full_env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        raise GitError(f"git 未安装，无法执行: {args[0] if args else 'git'}", 127)
    except subprocess.TimeoutExpired:
        raise GitError(f"git 命令超时: {' '.join(args)}", -1)
    if check and proc.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} 失败 (rc={proc.returncode}): {proc.stderr.strip()[:500]}",
            proc.returncode,
            proc.stderr,
        )
    return proc


# ── repo 状态 ─────────────────────────────────────────────────────────


def is_repo(root: Path) -> bool:
    """$workspace/memory 是否已是 git repo。"""
    return (root / ".git").is_dir()


def init_repo(root: Path) -> None:
    """初始化 $workspace/memory 为 git repo（幂等）。

    写 .gitignore、设 repo-local 身份（不依赖用户全局 git config）、
    commit.gpgsign=false（避免自动 commit 触发 GPG 签名失败）。
    """
    root.mkdir(parents=True, exist_ok=True)
    if is_repo(root):
        return
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(GITIGNORE_CONTENT, encoding="utf-8")
    # -b main：统一初始分支（不依赖 git 默认 master）；git<2.28 无 -b 时降级
    try:
        run_git(root, ["init", "-q", "-b", "main"])
    except GitError:
        run_git(root, ["init", "-q"])
        run_git(root, ["branch", "-M", "main"])
    run_git(root, ["config", "user.name", GIT_IDENTITY_NAME])
    run_git(root, ["config", "user.email", GIT_IDENTITY_EMAIL])
    run_git(root, ["config", "commit.gpgsign", "false"])
    run_git(root, ["config", "tag.gpgsign", "false"])
    # initial commit：捕获 .gitignore 与已有 vault 内容（捕获即历史起点）
    add_and_commit(root, "chore(vault): snapshot-of-vault-at-init")
    logger.info("git repo initialized at %s", root)


def is_dirty(root: Path, *, include_untracked: bool = True) -> bool:
    """工作区是否有未提交变更（含未跟踪文件）。"""
    args = ["status", "--porcelain"]
    if not include_untracked:
        args += ["--untracked-files=no"]
    proc = run_git(root, args, check=False)
    return bool(proc.stdout.strip()) if proc.returncode == 0 else True


def has_commits(root: Path) -> bool:
    """repo 是否已有至少一个 commit。"""
    proc = run_git(root, ["rev-list", "--count", "HEAD"], check=False)
    if proc.returncode != 0:
        return False
    return proc.stdout.strip() != "0"


def current_branch(root: Path) -> str:
    proc = run_git(root, ["rev-parse", "--abbrev-ref", "HEAD"], check=False)
    if proc.returncode != 0:
        return "main"
    return proc.stdout.strip() or "main"


def rename_current_branch(root: Path, target: str) -> bool:
    """把当前分支强制重命名为 target（git branch -M）。幂等。

    已在 target 直接返回 True；detached HEAD / 无分支等失败场景 log warning
    并返回 False，不阻塞主流程（调用方决定是否继续）。
    """
    target = target or "main"
    if not is_repo(root):
        logger.warning("rename_current_branch: %s 不是 git repo", root)
        return False
    if current_branch(root) == target:
        return True
    proc = run_git(root, ["branch", "-M", target], check=False)
    if proc.returncode != 0:
        logger.warning(
            "rename_current_branch: branch -M %s 失败: %s", target, proc.stderr.strip()[:300]
        )
        return False
    logger.info("renamed current branch to %s", target)
    return True


def add_and_commit(root: Path, message: str | None = None) -> bool:
    """git add -A && git commit。无变更时返回 False（不产 commit）。"""
    if not is_dirty(root):
        return False
    run_git(root, ["add", "-A"])
    msg = message or auto_commit_message()
    run_git(root, ["commit", "-q", "-m", msg])
    logger.info("committed: %s", msg)
    return True


def auto_commit_message() -> str:
    return f"chore(vault): auto-snapshot {datetime.datetime.now().isoformat(timespec='seconds')}"


def last_commit_time(root: Path) -> str | None:
    proc = run_git(root, ["log", "-1", "--pretty=format:%aI"], check=False)
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return proc.stdout.strip()


def log(root: Path, limit: int = 20) -> list[GitCommit]:
    proc = run_git(
        root,
        ["log", f"--max-count={max(limit, 1)}", "--pretty=format:%H|%aI|%s"],
        check=False,
    )
    commits: list[GitCommit] = []
    for line in proc.stdout.splitlines():
        if "|" in line:
            h, t, msg = line.split("|", 2)
            commits.append(GitCommit(hash=h, time=t, message=msg))
    return commits


def count_ahead_behind(root: Path, ref: str) -> tuple[int, int]:
    """本地 HEAD 与远端 ref 的领先/落后 commit 数（ref 不存在时返回 (0,0)）。"""
    proc = run_git(root, ["rev-list", "--left-right", "--count", f"HEAD...{ref}"], check=False)
    if proc.returncode != 0:
        return 0, 0
    parts = proc.stdout.split()
    if len(parts) != 2:
        return 0, 0
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return 0, 0


# ── remote 交互 ───────────────────────────────────────────────────────


def ensure_remote(root: Path, remote_url: str, name: str = "origin") -> None:
    if not remote_url:
        raise GitError("remote_url 未配置")
    proc = run_git(root, ["remote", "get-url", name], check=False)
    if proc.returncode != 0:
        run_git(root, ["remote", "add", name, remote_url])
    else:
        run_git(root, ["remote", "set-url", name, remote_url])


def fetch(root: Path, remote: str = "origin", **kw) -> None:
    run_git(root, ["fetch", remote], **kw)


def push(
    root: Path,
    remote: str = "origin",
    branch: str | None = None,
    *,
    force_with_lease: bool = True,
    **kw,
) -> None:
    """git push。默认 --force-with-lease（远端被他人更新则拒绝）。

    调用方负责在 push 前已 fetch（--force-with-lease 依赖 remote-tracking ref）。
    """
    branch = branch or current_branch(root)
    args = ["push"]
    if force_with_lease:
        args.append("--force-with-lease")
    args += [remote, branch]
    run_git(root, args, **kw)


def rebase(root: Path, upstream: str) -> tuple[bool, list[str]]:
    """git rebase <upstream>。成功返回 (True, [])；冲突则 abort 并返回 (False, conflicts)。"""
    proc = run_git(root, ["rebase", upstream], check=False)
    if proc.returncode == 0:
        return True, []
    conflicts = _merge_conflict_files(root)
    # 中止 rebase，回到 rebase 前状态，交由用户决定 hard reset
    run_git(root, ["rebase", "--abort"], check=False)
    return False, conflicts


def _merge_conflict_files(root: Path) -> list[str]:
    proc = run_git(root, ["diff", "--name-only", "--diff-filter=U"], check=False)
    return [line for line in proc.stdout.splitlines() if line.strip()]


def checkout_to_backup_branch(root: Path, commit_hash: str) -> str:
    """把指定历史版本创建一个 backup 分支（不切换工作区，不覆盖当前文件）。"""
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    branch = f"backup/restore-{ts}"
    run_git(root, ["branch", branch, commit_hash])
    return branch


def hard_reset(root: Path, remote: str, branch: str) -> None:
    """git reset --hard <remote>/<branch>（丢弃本地提交，回退到远端）。"""
    run_git(root, ["reset", "--hard", f"{remote}/{branch}"])


# ── status 聚合 ───────────────────────────────────────────────────────


def repo_status(root: Path, *, remote_configured: bool, branch: str = "main") -> dict:
    """聚合 /version/status 用到的字段。"""
    if not is_repo(root):
        return {
            "initialized": False,
            "dirty": False,
            "has_commits": False,
            "last_commit_at": None,
            "remote_configured": remote_configured,
            "ahead": 0,
            "behind": 0,
        }
    ahead, behind = 0, 0
    if remote_configured:
        ahead, behind = count_ahead_behind(root, f"origin/{branch}")
    return {
        "initialized": True,
        "dirty": is_dirty(root),
        "has_commits": has_commits(root),
        "last_commit_at": last_commit_time(root),
        "remote_configured": remote_configured,
        "ahead": ahead,
        "behind": behind,
    }