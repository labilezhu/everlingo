# ref: docs/i18n/i18n.md — Phase 7 Memory Vault 版本控制后端文案 i18n
# 版本控制子系统（git.py / restore.py / committer.py / indexer /version/* 端点 /
# gateway backup_api.py）中「直接下发给用户」的文案字典与取值函数。
# 边界：git CLI 自身输出的 stderr（英文）按原样拼接，不做翻译；
# logger.warning/info 等纯后端日志不属于用户可见文案，不在此列。

from __future__ import annotations

FALLBACK_LANG = "en"


# {lang: {key: text}}。key 缺失 lang 回退 FALLBACK_LANG；lang 与 key 均缺失回退 key 本身。
# 支持 {placeholder} 占位，由 version_t() 的 kwargs 通过 .format() 填充。
VERSION_MESSAGES: dict[str, dict[str, str]] = {
    "zh-CN": {
        "git_not_installed": "git 未安装，无法执行: {cmd}",
        "git_timeout": "git 命令超时: {args}",
        "git_command_failed": "git {args} 失败 (rc={returncode}): {stderr}",
        "remote_url_missing": "remote_url 未配置",
        "remote_reachable": "远端可达，检测到 {count} 个分支头",
        "ls_remote_failed": "ls-remote 失败 (rc={returncode})",
        "repo_not_initialized": "memory repo 未初始化，无法恢复",
        "repo_not_initialized_short": "repo 未初始化",
        "pre_restore_commit_failed": "pre-restore commit 失败: {error}",
        "fetch_failed": "fetch 失败: {error}",
        "rebased_to_remote": "已 rebase 到远端",
        "conflict_saved_to_backup": "远端与本地冲突，已保存到 backup 分支，请确认后 hard reset",
        "committer_not_started": "committer 未启动",
        "checked_out_backup_branch": "已检出到 backup 分支 {branch}",
        "hard_reset_done": "hard reset 完成",
        "hard_reset_failed": "hard reset 失败",
        "indexer_unreachable": "{what} 失败：indexer 不可达或返回异常",
        "unsupported_auth_method": "不支持凭证模式 {method}（可选：ssh / https_pat / https_none）",
    },
    "en": {
        "git_not_installed": "git is not installed, cannot run: {cmd}",
        "git_timeout": "git command timed out: {args}",
        "git_command_failed": "git {args} failed (rc={returncode}): {stderr}",
        "remote_url_missing": "remote_url is not configured",
        "remote_reachable": "remote reachable, detected {count} branch head(s)",
        "ls_remote_failed": "ls-remote failed (rc={returncode})",
        "repo_not_initialized": "memory repo not initialized, cannot restore",
        "repo_not_initialized_short": "repo not initialized",
        "pre_restore_commit_failed": "pre-restore commit failed: {error}",
        "fetch_failed": "fetch failed: {error}",
        "rebased_to_remote": "rebased to remote",
        "conflict_saved_to_backup": (
            "remote and local conflict; changes saved to a backup branch, "
            "please confirm before a hard reset"
        ),
        "committer_not_started": "committer not started",
        "checked_out_backup_branch": "checked out to backup branch {branch}",
        "hard_reset_done": "hard reset done",
        "hard_reset_failed": "hard reset failed",
        "indexer_unreachable": "{what} failed: indexer unreachable or returned an error",
        "unsupported_auth_method": (
            "unsupported auth method {method} (options: ssh / https_pat / https_none)"
        ),
    },
}


def version_t(key: str, interface_language: str | None, **kwargs: str) -> str:
    """按界面语言取版本控制文案；lang 缺失回退 en，key 缺失回退 key 本身。

    interface_language 为 None（非 UI 调用 / 测试缺省）时按 en 处理。
    kwargs 用于 {placeholder} 占位填充（.format()）。
    """
    template = VERSION_MESSAGES.get(interface_language or "", {}).get(key)
    if template is None:
        template = VERSION_MESSAGES.get(FALLBACK_LANG, {}).get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            # 占位不匹配时不抛错，原样返回模板
            return template
    return template
