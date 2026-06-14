from everlingo.models import UserProfile
from everlingo.intent import IntentAnalyzer


def test_word_lookup_english_target_single_word():
    profile = UserProfile(interface_language="zh-CN", target_language="en")
    analyzer = IntentAnalyzer(profile)
    assert analyzer.analyze("hello") == "word"


def test_translation_english_target_multiple_words():
    profile = UserProfile(interface_language="zh-CN", target_language="en")
    analyzer = IntentAnalyzer(profile)
    assert analyzer.analyze("how are you") == "translation"


def test_word_lookup_chinese_target_single_word():
    profile = UserProfile(interface_language="en", target_language="zh-CN")
    analyzer = IntentAnalyzer(profile)
    assert analyzer.analyze("你好") == "word"


def test_translation_chinese_target_multiple_chars():
    profile = UserProfile(interface_language="en", target_language="zh-CN")
    analyzer = IntentAnalyzer(profile)
    assert analyzer.analyze("今天天气真好") == "translation"


def test_unknown_input_mixed_languages():
    profile = UserProfile(interface_language="zh-CN", target_language="en")
    analyzer = IntentAnalyzer(profile)
    assert analyzer.analyze("hello 你好") == "unknown"


def test_empty_input():
    profile = UserProfile(interface_language="zh-CN", target_language="en")
    analyzer = IntentAnalyzer(profile)
    assert analyzer.analyze("") == "unknown"
    assert analyzer.analyze("   ") == "unknown"


def test_whitespace_around_input():
    profile = UserProfile(interface_language="zh-CN", target_language="en")
    analyzer = IntentAnalyzer(profile)
    assert analyzer.analyze("  hello  ") == "word"
    assert analyzer.analyze("  how are you  ") == "translation"


def test_chinese_characters_detection():
    profile = UserProfile(interface_language="en", target_language="zh-CN")
    analyzer = IntentAnalyzer(profile)
    assert analyzer.analyze("学习") == "word"
    assert analyzer.analyze("我正在学习中文") == "translation"
