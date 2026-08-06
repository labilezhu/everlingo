# ref: docs/i18n/i18n.md — Phase 2 Chat Agent 兜底文案 i18n

from everlingo.i18n import FALLBACK_LANG, MESSAGES, t


def test_zh_returns_chinese():
    assert t("error_generic", "zh-CN") == "出错了，请稍后重试"


def test_en_returns_english():
    assert t("error_generic", "en") == "Something went wrong, please try again later"


def test_unknown_lang_falls_back_to_en():
    # 未来扩到 ja/fr/de 等界面语言时，缺失 lang 回退 en
    assert t("error_generic", "ja") == t("error_generic", "en")


def test_unknown_key_returns_key_itself():
    assert t("no_such_key", "en") == "no_such_key"
    assert t("no_such_key", "zh-CN") == "no_such_key"


def test_empty_lang_falls_back_to_en():
    # 空 language 不应抛错
    assert t("error_generic", "") == t("error_generic", "en")


def test_format_placeholder():
    assert t("error_retry", "zh-CN", error="boom") == "出错了，请稍后重试: boom"
    assert t("error_retry", "en", error="boom") == (
        "Something went wrong, please try again later: boom"
    )


def test_format_without_kwargs_keeps_placeholder():
    # 未传 kwargs 时保持模板里的 {error} 原样
    assert "{error}" in t("error_retry", "en")


def test_format_mismatched_kwargs_no_crash():
    # 传入多余/缺失占位不抛错
    assert t("ai_unavailable", "zh-CN", extra="x") == (
        "AI 服务暂时不可用，请稍后重试 (已自动重试 2 次)"
    )


def test_all_languages_have_same_keys():
    """所有语言的 key 集合一致，避免某语言漏译。"""
    key_sets = [frozenset(msgs.keys()) for msgs in MESSAGES.values()]
    assert all(ks == key_sets[0] for ks in key_sets[1:])


def test_fallback_lang_is_en_and_present():
    assert FALLBACK_LANG == "en"
    assert "en" in MESSAGES