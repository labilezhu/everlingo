# ref: docs/impl-spec/worksplace/vault-version-control.md §3 — Committer（indexer 进程内）
# 独立定时器，不订阅 watcher 事件：
#   * 每 tick（≤ commit_interval）跑 `git status --porcelain`，dirty 才 commit；
#   * commit 后按 push_interval 自动 push --force-with-lease（enabled 时才 push）；
#   * start() 时若 git 可用：init repo（懒加载）+ initial commit 兜底；
#   * atexit + stop() 前 final commit（防止 dirty 丢失）。

from __future__ import annotations

import atexit
import logging
import threading
import time as _time
from pathlib import Path

from everlingo.i18n.version import version_t
from everlingo.models import GitBackup

from . import git
from .ssh_key import SSHCommandContext

logger = logging.getLogger(__name__)


# atexit 兜底 final commit 的活动 repo root 集合（Committer.start 注册 / stop 移除）。
# 只提交进程内实际 start 过的 memory repo，避免误提交任意目录。
_atexit_root_lock = threading.Lock()
_atexit_roots: set[Path] = set()


def _default_lang() -> str:
    """后台 push（无请求上下文）时取当前 resolved 界面语言；异常兜底 en。"""
    try:
        from everlingo import setting

        return setting.load_resolved_profile().language.interface_language
    except Exception:  # noqa: BLE001
        return "en"


class Committer:
    """Memory Vault 自动 commit / push 调度器。仅 indexer 进程内实例化。"""

    # 手动触发 commit 的最小间隔（秒），防止连点造成空 commit
    MIN_MANUAL_COMMIT_INTERVAL = 5.0

    def __init__(
        self,
        memory_root: Path,
        backup: GitBackup | None = None,
        *,
        tick_seconds: float = 5.0,
    ) -> None:
        self._root = Path(memory_root)
        self._backup = backup or self._load_backup_or_default()
        self._tick = tick_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._last_push_at: float = 0.0
        self._ssh = SSHCommandContext()

    @staticmethod
    def _load_backup_or_default() -> GitBackup:
        try:
            from everlingo import setting

            return setting.load_git_backup()
        except Exception:  # noqa: BLE001
            return GitBackup()

    # ── 生命周期 ─────────────────────────────────────────────────────

    def _ensure_repo(self) -> None:
        """init repo（懒加载）+ initial commit 兜底 + 统一本地分支名。幂等。"""
        if not git.git_available():
            return
        try:
            git.init_repo(self._root)
            # 启动强制统一本地分支名 = 配置 branch，保证 push/fetch/rebase/status 全链路自洽
            git.rename_current_branch(self._root, self._backup.branch)
            if not git.has_commits(self._root):
                self._commit_now("chore(vault): snapshot-of-vault-at-init")
        except Exception as e:  # noqa: BLE001
            logger.warning("committer: init repo 失败: %s", e)

    def start(self) -> None:
        """启动定时器线程。已在跑则 no-op。"""
        if self.running:
            return
        self._backup = self._load_backup_or_default()
        self._ssh.configure(
            method=self._backup.auth.method,
            ssh_private_key_file=self._backup.auth.ssh_private_key_file,
            pat=self._backup.auth.pat,
        )
        with _atexit_root_lock:
            _atexit_roots.add(self._root)
        # init repo（懒加载）+ initial commit 兜底（即使 enabled=false）
        self._ensure_repo()
        if not self._backup.enabled:
            logger.info("git_backup 未启用，committer 定时器不启动")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="vault-committer",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "committer started (tick=%ss push_interval=%ss)",
            self._backup.commit_interval,
            self._backup.push_interval,
        )

    def stop(self) -> None:
        """停止定时器并做 final commit。幂等。"""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        # final commit（无论 enabled，防止 dirty 丢失）
        if git.git_available():
            try:
                self._commit_now("chore(vault): final-snapshot")
            except Exception as e:  # noqa: BLE001
                logger.warning("committer: final commit 失败: %s", e)
        with _atexit_root_lock:
            _atexit_roots.discard(self._root)
        self._ssh.close()

    def apply_config(self, backup: GitBackup) -> None:
        """用传入配置替换内存副本并同步定时线程启停。GIL 保护，幂等。

        供 indexer `/version/apply-config`（gateway 保存 everlingo.yaml 后
        热重载 committer）与 CoW 多副本写入使用，避免重启进程才生效。
        """
        with self._lock:
            self._backup = backup
            self._ssh.configure(
                method=backup.auth.method,
                ssh_private_key_file=backup.auth.ssh_private_key_file,
                pat=backup.auth.pat,
            )
            if backup.enabled:
                with _atexit_root_lock:
                    _atexit_roots.add(self._root)
                if self._thread is not None and self._thread.is_alive():
                    logger.info("apply_config: committer 已在运行，仅更新配置")
                else:
                    self._ensure_repo()
                    self._stop_event.clear()
                    self._thread = threading.Thread(
                        target=self._run_loop,
                        name="vault-committer",
                        daemon=True,
                    )
                    self._thread.start()
                    logger.info(
                        "apply_config: committer 定时器启动 (tick=%ss push_interval=%ss)",
                        backup.commit_interval,
                        backup.push_interval,
                    )
            else:
                if self._thread is not None:
                    self._stop_event.set()
                    self._thread.join(timeout=5.0)
                    self._thread = None
                    logger.info("apply_config: committer 定时器停止")

    def reload_config(self) -> GitBackup:
        """重新从 everlingo.yaml 读取 git_backup，应用生效。返回新配置。"""
        backup = self._load_backup_or_default()
        self.apply_config(backup)
        return backup

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── 定时循环 ─────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self._stop_event.wait(self._tick)
            if self._stop_event.is_set():
                break  # 正在 shutdown：把最后一个 commit 留给 stop() 的 final commit
            try:
                self.poll_commit()
            except Exception as e:  # noqa: BLE001
                logger.warning("committer commit tick 失败: %s", e)
            if self._backup.enabled:
                try:
                    self.poll_push()
                except Exception as e:  # noqa: BLE001
                    logger.warning("committer push tick 失败: %s", e)

    def poll_commit(self) -> bool:
        """一次 commit 检查：dirty 则 commit。返回是否产生了 commit。"""
        if not git.git_available() or not git.is_repo(self._root):
            return False
        if not git.is_dirty(self._root):
            return False
        if not self._backup.enabled:
            # enabled=false：仅做 initial commit 兜底，不继续
            if not git.has_commits(self._root):
                return self._commit_now("chore(vault): snapshot-of-vault-at-init")
            return False
        return self._commit_now()

    def _commit_now(self, message: str | None = None) -> bool:
        with self._lock:
            return git.add_and_commit(self._root, message)

    # ── push ─────────────────────────────────────────────────────────

    def poll_push(self) -> bool:
        """push 检查：enabled 且超过 push_interval 才 push。返回是否尝试了 push。"""
        if not self._backup.enabled or not self._backup.remote_url:
            return False
        if self._backup.push_interval <= 0:
            return False  # 0 = 仅手动触发
        now = _time.monotonic()
        if self._last_push_at and (now - self._last_push_at) < self._backup.push_interval:
            return False
        try:
            self.push_now()
            self._last_push_at = now
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("committer push 失败: %s", e)
            return False

    def push_now(self, *, force: bool = False, interface_language: str | None = None) -> bool:
        """强制 push 一次（默认 --force-with-lease；force=True → --force）。返回是否成功。"""
        lang = interface_language or _default_lang()
        if not self._backup.remote_url:
            raise git.GitError(version_t("remote_url_missing", lang))
        git.ensure_remote(self._root, self._backup.remote_url, interface_language=lang)
        env, config = self._remote_ctx()
        git.fetch(self._root, env=env, config=config, interface_language=lang)
        git.push(
            self._root,
            remote="origin",
            branch=self._backup.branch,
            force=force,
            env=env,
            config=config,
            interface_language=lang,
        )
        self._last_push_at = _time.monotonic()
        return True

    def force_push_now(self, *, interface_language: str | None = None) -> bool:
        """无条件强推一次（git push --force，覆盖远端历史）。"""
        return self.push_now(force=True, interface_language=interface_language)

    def _remote_ctx(self) -> tuple[dict[str, str], dict[str, str]]:
        """按当前 auth 构造 git 需要注入的 env + config。"""
        self._ssh.configure(
            method=self._backup.auth.method,
            ssh_private_key_file=self._backup.auth.ssh_private_key_file,
            pat=self._backup.auth.pat,
        )
        self._ssh.start()
        extra = self._ssh.extraheader() or {}
        return self._ssh.env(), extra


# ── 安全网辅助 ───────────────────────────────────────────────────────


def ensure_snapshot(memory_root: Path, message: str | None = None) -> bool:
    """独立安全网 commit：供 reset_vault 等路径在覆盖文件前保存历史。

    init（首次会连 initial commit 一起捕获）+ 累加当前变更；任一步骤真实
    产生了 commit 即返回 True。幂等：无变更且已存在时返回 False。
    git 不可用时返回 False。
    """
    root = Path(memory_root)
    if not git.git_available():
        return False
    try:
        existed = git.is_repo(root)
        git.init_repo(root)
        made_init = not existed
        made = git.add_and_commit(root, message)
        return made_init or made
    except Exception as e:  # noqa: BLE001
        logger.warning("snapshot_memory 失败: %s", e)
        return False


# atexit 兜底 final commit（uvicorn 收到 SIGTERM 走 lifespan close 前，进程退出仍保底）
# 仅提交进程内实际 start 过的 memory repo（见 _atexit_roots），避免残留 dirty 丢失。


def _final_snapshot() -> None:
    if not git.git_available():
        return
    with _atexit_root_lock:
        roots = list(_atexit_roots)
    for root in roots:
        try:
            if git.is_repo(root):
                git.add_and_commit(root, "chore(vault): final-snapshot")
        except Exception:  # noqa: BLE001
            pass


atexit.register(_final_snapshot)