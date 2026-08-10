# ref: docs/impl-spec/worksplace/vault-version-control.md — Memory Vault 版本控制与远端备份
# 本包提供对 $workspace/memory git repo 的操作封装：
#   git.py      subprocess git CLI 封装（init/status/commit/push/fetch/rebase/log/...）
#   committer.py indexer 进程内的自动 commit + push 定时器
#   ssh_key.py  远端凭证解析（ssh GIT_SSH_COMMAND / https_pat extraheader）
#   restore.py   恢复流程：commit → fetch → rebase → 冲突打 backup 分支
#
# 仅 indexer 进程内加载（committer / 端点使用）；gateway 进程经 HTTP 委托、不 import 本包。

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def git_available() -> bool:
    from .git import git_available as _ga

    return _ga()


def snapshot_memory(message: str | None = None) -> bool:
    """独立的安全网 commit：初始化 memory repo（如无）并提交当前变更。

    供 reset_vault 等内部路径在覆盖文件前保存历史（即使 committer 未启动）。
    幂等：无变更时不产生 commit。git 不可用 / 失败时返回 False。
    """
    from everlingo import workspace

    from .committer import ensure_snapshot

    return ensure_snapshot(workspace.memory_dir(), message)