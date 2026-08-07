# ref: docs/i18n/i18n.md — Vault 内容 i18n（events 文件前置内容）

from everlingo.i18n.vault import EVENT_FILE_PREAMBLE, FALLBACK_LANG, event_file_preamble


def test_zh_returns_chinese():
    assert event_file_preamble("zh-CN").startswith("# 当天事件")
    assert "事件按时间顺序记录" in event_file_preamble("zh-CN")


def test_en_returns_english():
    assert event_file_preamble("en").startswith("# Today's Events")
    assert "chronological" in event_file_preamble("en")


def test_unknown_lang_falls_back_to_en():
    assert event_file_preamble("ja") == event_file_preamble("en")


def test_empty_lang_falls_back_to_en():
    assert event_file_preamble("") == event_file_preamble("en")


def test_fallback_lang_is_en_and_present():
    assert FALLBACK_LANG == "en"
    assert "en" in EVENT_FILE_PREAMBLE


def test_all_languages_have_content():
    for lang in ("zh-CN", "en"):
        assert EVENT_FILE_PREAMBLE[lang].strip()