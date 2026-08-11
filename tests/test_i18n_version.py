# ref: docs/i18n/i18n.md — Phase 7 版本控制后端文案 i18n
# 与 tests/test_i18n.py（Phase 2 messages）同构：验证 VERSION_MESSAGES 字典一致性、
# version_t 回退与占位填充。

import re

from everlingo.i18n.version import VERSION_MESSAGES, version_t

_PLACEHOLDER_RE = re.compile(r"{(\w+)}")


def test_zh_returns_chinese():
    assert version_t("remote_url_missing", "zh-CN") == "remote_url 未配置"
    assert version_t("committer_not_started", "zh-CN") == "committer 未启动"


def test_en_returns_english():
    assert version_t("remote_url_missing", "en") == "remote_url is not configured"
    assert version_t("committer_not_started", "en") == "committer not started"


def test_none_lang_falls_back_to_en():
    # 非 UI 调用 / 测试缺省 interface_language=None → en
    assert version_t("remote_url_missing", None) == version_t("remote_url_missing", "en")


def test_unknown_lang_falls_back_to_en():
    assert version_t("remote_url_missing", "ja") == version_t("remote_url_missing", "en")


def test_unknown_key_returns_key_itself():
    assert version_t("no_such_key", "en") == "no_such_key"
    assert version_t("no_such_key", "zh-CN") == "no_such_key"


def test_format_placeholder():
    assert version_t("git_command_failed", "zh-CN", args="push", returncode="1", stderr="boom") == (
        "git push 失败 (rc=1): boom"
    )
    assert version_t(
        "git_command_failed", "en", args="push", returncode="1", stderr="boom"
    ) == "git push failed (rc=1): boom"
    assert version_t("remote_reachable", "zh-CN", count="2") == "远端可达，检测到 2 个分支头"
    assert version_t("checked_out_backup_branch", "en", branch="backup/restore-1") == (
        "checked out to backup branch backup/restore-1"
    )


def test_format_without_kwargs_keeps_placeholder():
    assert "{returncode}" in version_t("git_command_failed", "en")


def test_format_mismatched_kwargs_no_crash():
    assert version_t("hard_reset_done", "zh-CN", extra="x") == "hard reset 完成"


def test_all_languages_have_same_keys():
    """所有语言的 key 集合一致，避免某语言漏译。"""
    key_sets = [frozenset(msgs.keys()) for msgs in VERSION_MESSAGES.values()]
    assert all(ks == key_sets[0] for ks in key_sets[1:])


def test_placeholders_consistent_across_languages():
    """同一 key 各语言的占位符集合一致（format 参数可共用）。"""
    langs = list(VERSION_MESSAGES.values())
    for key in langs[0]:
        placeholder_sets = {
            frozenset(_PLACEHOLDER_RE.findall(text)) for text in [msgs[key] for msgs in langs]
        }
        assert len(placeholder_sets) == 1, f"key={key} 占位符不一致"
