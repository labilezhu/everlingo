from unittest.mock import MagicMock

from langchain_core.messages import AIMessage

from everlingo.models import UserProfile
from everlingo.trans_teacher import TranslationTeacher


def _make_mock_agent(text: str):
    mock_agent = MagicMock()
    mock_agent.invoke.return_value = {"messages": [AIMessage(content=text)]}
    return mock_agent


def test_trans_teacher_returns_translation_record():
    mock_agent = _make_mock_agent("mock translation")
    profile = UserProfile(interface_language="zh-CN", target_language="en")
    teacher = TranslationTeacher(mock_agent, profile)
    result = teacher.translate("hello world")
    assert result.source_text == "hello world"
    assert result.target_text == "mock translation"
    assert result.source_lang == "en"
    assert result.target_lang == "zh-CN"


def test_trans_teacher_chinese_to_english():
    mock_agent = _make_mock_agent("mock en translation")
    profile = UserProfile(interface_language="en", target_language="zh-CN")
    teacher = TranslationTeacher(mock_agent, profile)
    result = teacher.translate("你好世界")
    assert result.source_text == "你好世界"
    assert result.target_text == "mock en translation"
    assert result.target_lang == "en"
    assert result.source_lang == "zh-CN"


def test_lang_display_name():
    assert TranslationTeacher._lang_display_name("en") == "英语"
    assert TranslationTeacher._lang_display_name("zh-CN") == "简体中文"
    assert TranslationTeacher._lang_display_name("unknown") == "unknown"
