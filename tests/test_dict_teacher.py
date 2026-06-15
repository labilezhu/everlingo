from unittest.mock import MagicMock

from langchain_core.messages import AIMessage

from everlingo.models import UserProfile
from everlingo.dict_teacher import DictionaryTeacher


def _make_mock_agent(text: str):
    mock_agent = MagicMock()
    mock_agent.invoke.return_value = {"messages": [AIMessage(content=text)]}
    return mock_agent


def test_dict_teacher_returns_word_query():
    mock_agent = _make_mock_agent("mock response")
    profile = UserProfile(interface_language="zh-CN", target_language="en")
    teacher = DictionaryTeacher(mock_agent, profile)
    result = teacher.lookup("hello")
    assert result.word == "hello"
    assert result.definition == "mock response"
    assert result.interface_language == "zh-CN"


def test_dict_teacher_with_scene():
    mock_agent = _make_mock_agent("mock with scene")
    profile = UserProfile(interface_language="zh-CN", target_language="en")
    teacher = DictionaryTeacher(mock_agent, profile)
    result = teacher.lookup("hello", scene="在邮件中看到")
    assert result.word == "hello"
    assert result.scene == "在邮件中看到"
    assert result.definition == "mock with scene"


def test_lang_display_name():
    assert DictionaryTeacher._lang_display_name("en") == "英语"
    assert DictionaryTeacher._lang_display_name("zh-CN") == "简体中文"
    assert DictionaryTeacher._lang_display_name("unknown") == "unknown"
