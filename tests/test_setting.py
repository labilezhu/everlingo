import pytest
from pydantic import ValidationError

from everlingo.models import (
    EverLingoSetting,
    LoggingSetting,
    SysSetting,
    TracingSetting,
    UserBackground,
    UserLanguage,
    UserProfile,
)
from everlingo.setting import dict_to_setting, setting_to_dict


def test_empty_profile_is_incomplete():
    profile = UserProfile()
    assert not profile.is_complete()
    errors = profile.validate()
    assert len(errors) == 2


def test_partial_profile_is_incomplete():
    profile = UserProfile(language=UserLanguage(interface_language="zh-CN"))
    assert not profile.is_complete()
    errors = profile.validate()
    assert len(errors) == 1
    assert "目标学习语言" in errors[0]


def test_complete_profile():
    profile = UserProfile(
        language=UserLanguage(interface_language="zh-CN", target_language="en")
    )
    assert profile.is_complete()
    assert profile.validate() == []


def test_same_languages_not_allowed():
    profile = UserProfile(
        language=UserLanguage(interface_language="zh-CN", target_language="zh-CN")
    )
    errors = profile.validate()
    assert len(errors) == 1
    assert "不能相同" in errors[0]


def test_japanese_zh_profile():
    """日本語界面，学习中文的用户配置"""
    profile = UserProfile(
        language=UserLanguage(interface_language="ja", target_language="zh-CN")
    )
    assert profile.is_complete()
    assert profile.validate() == []


def test_zh_japanese_profile():
    """中文界面，学习日本語的用户配置"""
    profile = UserProfile(
        language=UserLanguage(interface_language="zh-CN", target_language="ja")
    )
    assert profile.is_complete()
    assert profile.validate() == []


def test_en_japanese_profile():
    """英文界面，学习日本語的用户配置"""
    profile = UserProfile(
        language=UserLanguage(interface_language="en", target_language="ja")
    )
    assert profile.is_complete()
    assert profile.validate() == []


def test_profile_with_background():
    profile = UserProfile(
        language=UserLanguage(interface_language="zh-CN", target_language="en"),
        background=UserBackground(
            hobbies="历史与文艺",
            residence="北京",
            gender="male",
        ),
        dictionary_definition_style="- 词意\n- 词源",
    )
    assert profile.is_complete()
    assert profile.background.hobbies == "历史与文艺"
    assert profile.background.residence == "北京"
    assert profile.background.gender == "male"
    assert profile.dictionary_definition_style == "- 词意\n- 词源"


def test_sys_setting_defaults():
    ss = SysSetting()
    assert ss.openai_api_key == ""
    assert ss.openai_base_url == ""
    assert ss.openai_model == ""


def test_everlingo_setting_defaults():
    setting = EverLingoSetting()
    assert setting.sys_setting.openai_api_key == ""
    assert setting.user_profile.language.interface_language == ""


def test_everlingo_setting_full():
    setting = EverLingoSetting(
        sys_setting=SysSetting(
            openai_api_key="sk-test",
            openai_base_url="https://test.api.com",
            openai_model="gpt-4",
        ),
        user_profile=UserProfile(
            language=UserLanguage(interface_language="zh-CN", target_language="en"),
        ),
    )
    assert setting.sys_setting.openai_api_key == "sk-test"
    assert setting.sys_setting.openai_base_url == "https://test.api.com"
    assert setting.sys_setting.openai_model == "gpt-4"
    assert setting.user_profile.language.interface_language == "zh-CN"
    assert setting.user_profile.language.target_language == "en"


def test_everlingo_setting_with_japanese():
    setting = EverLingoSetting(
        user_profile=UserProfile(
            language=UserLanguage(interface_language="zh-CN", target_language="ja"),
        ),
    )
    assert setting.user_profile.language.interface_language == "zh-CN"
    assert setting.user_profile.language.target_language == "ja"


def test_logging_setting_defaults():
    ls = LoggingSetting()
    assert ls.log_file == ""
    assert ls.log_level == "debug"


def test_sys_setting_contains_logging():
    # logging_setting 是 sys_setting 的子字段，ref: configuration.md
    ss = SysSetting(
        logging_setting=LoggingSetting(
            log_file="/tmp/everlingo.log",
            log_level="info",
        ),
    )
    assert ss.logging_setting.log_file == "/tmp/everlingo.log"
    assert ss.logging_setting.log_level == "info"


def test_everlingo_setting_with_logging():
    setting = EverLingoSetting(
        sys_setting=SysSetting(
            logging_setting=LoggingSetting(
                log_file="/tmp/everlingo.log",
                log_level="info",
            ),
        ),
    )
    assert setting.sys_setting.logging_setting.log_file == "/tmp/everlingo.log"
    assert setting.sys_setting.logging_setting.log_level == "info"


def test_dict_to_setting_includes_logging():
    # logging_setting 嵌套在 sys_setting 下，ref: configuration.md yaml 结构
    data = {
        "sys_setting": {
            "logging_setting": {
                "log_file": "/custom/path.log",
                "log_level": "warn",
            },
        },
    }
    setting = dict_to_setting(data)
    assert setting.sys_setting.logging_setting.log_file == "/custom/path.log"
    assert setting.sys_setting.logging_setting.log_level == "warn"


def test_setting_to_dict_includes_logging():
    setting = EverLingoSetting(
        sys_setting=SysSetting(
            logging_setting=LoggingSetting(
                log_file="/custom/path.log",
                log_level="error",
            ),
        ),
    )
    d = setting_to_dict(setting)
    assert d["sys_setting"]["logging_setting"]["log_file"] == "/custom/path.log"
    assert d["sys_setting"]["logging_setting"]["log_level"] == "error"


def test_logging_roundtrip():
    original = EverLingoSetting(
        sys_setting=SysSetting(
            openai_api_key="sk-test",
            logging_setting=LoggingSetting(log_file="/log/test.log", log_level="info"),
        ),
        user_profile=UserProfile(
            language=UserLanguage(interface_language="zh-CN", target_language="en")
        ),
    )
    d = setting_to_dict(original)
    restored = dict_to_setting(d)
    assert restored.sys_setting.logging_setting.log_file == "/log/test.log"
    assert restored.sys_setting.logging_setting.log_level == "info"


def test_tracing_setting_defaults():
    ts = TracingSetting()
    assert ts.tracing_service == ""
    assert ts.langfuse_secret_key == ""
    assert ts.langfuse_public_key == ""
    assert ts.langfuse_base_url == ""


def test_sys_setting_contains_tracing():
    # tracing_setting 是 sys_setting 的子字段，ref: configuration.md
    ss = SysSetting(
        tracing_setting=TracingSetting(
            tracing_service="langfuse",
            langfuse_secret_key="sk-lf-test",
            langfuse_public_key="pk-lf-test",
            langfuse_base_url="http://localhost:3300",
        ),
    )
    assert ss.tracing_setting.tracing_service == "langfuse"


def test_everlingo_setting_with_tracing():
    setting = EverLingoSetting(
        sys_setting=SysSetting(
            tracing_setting=TracingSetting(
                tracing_service="langfuse",
                langfuse_secret_key="sk-lf-test",
                langfuse_public_key="pk-lf-test",
                langfuse_base_url="http://localhost:3300",
            ),
        ),
    )
    assert setting.sys_setting.tracing_setting.tracing_service == "langfuse"
    assert setting.sys_setting.tracing_setting.langfuse_secret_key == "sk-lf-test"
    assert setting.sys_setting.tracing_setting.langfuse_public_key == "pk-lf-test"
    assert setting.sys_setting.tracing_setting.langfuse_base_url == "http://localhost:3300"


def test_dict_to_setting_includes_tracing():
    # tracing_setting 嵌套在 sys_setting 下，ref: configuration.md yaml 结构
    data = {
        "sys_setting": {
            "tracing_setting": {
                "tracing_service": "langfuse",
                "langfuse_secret_key": "sk-lf-test",
                "langfuse_public_key": "pk-lf-test",
                "langfuse_base_url": "http://localhost:3300",
            },
        },
    }
    setting = dict_to_setting(data)
    assert setting.sys_setting.tracing_setting.tracing_service == "langfuse"
    assert setting.sys_setting.tracing_setting.langfuse_secret_key == "sk-lf-test"
    assert setting.sys_setting.tracing_setting.langfuse_public_key == "pk-lf-test"
    assert setting.sys_setting.tracing_setting.langfuse_base_url == "http://localhost:3300"


def test_setting_to_dict_includes_tracing():
    setting = EverLingoSetting(
        sys_setting=SysSetting(
            tracing_setting=TracingSetting(
                tracing_service="langfuse",
                langfuse_secret_key="sk-lf-test",
                langfuse_public_key="pk-lf-test",
                langfuse_base_url="http://localhost:3300",
            ),
        ),
    )
    d = setting_to_dict(setting)
    assert d["sys_setting"]["tracing_setting"]["tracing_service"] == "langfuse"
    assert d["sys_setting"]["tracing_setting"]["langfuse_secret_key"] == "sk-lf-test"
    assert d["sys_setting"]["tracing_setting"]["langfuse_public_key"] == "pk-lf-test"
    assert d["sys_setting"]["tracing_setting"]["langfuse_base_url"] == "http://localhost:3300"


def test_tracing_roundtrip():
    original = EverLingoSetting(
        sys_setting=SysSetting(
            tracing_setting=TracingSetting(
                tracing_service="langfuse",
                langfuse_secret_key="sk-lf-test",
                langfuse_public_key="pk-lf-test",
                langfuse_base_url="http://localhost:3300",
            ),
        ),
    )
    d = setting_to_dict(original)
    restored = dict_to_setting(d)
    assert restored.sys_setting.tracing_setting.tracing_service == "langfuse"
    assert restored.sys_setting.tracing_setting.langfuse_secret_key == "sk-lf-test"
    assert restored.sys_setting.tracing_setting.langfuse_public_key == "pk-lf-test"
    assert restored.sys_setting.tracing_setting.langfuse_base_url == "http://localhost:3300"


def test_user_profile_japanese_yaml_roundtrip():
    # 验证日语语言设置在 YAML roundtrip 中的正确性
    data = {
        "user_profile": {
            "language": {
                "interface_language": "zh-CN",
                "target_language": "ja",
            },
        }
    }
    setting = dict_to_setting(data)
    assert setting.user_profile.language.interface_language == "zh-CN"
    assert setting.user_profile.language.target_language == "ja"
    d = setting_to_dict(setting)
    assert d["user_profile"]["language"]["interface_language"] == "zh-CN"
    assert d["user_profile"]["language"]["target_language"] == "ja"


def test_user_profile_yaml_roundtrip():
    # 验证 UserProfile 与 YAML 结构对齐：language/background 嵌套，ref: everlingo.example.yaml
    data = {
        "user_profile": {
            "language": {
                "interface_language": "zh-CN",
                "target_language": "en",
            },
            "background": {
                "hobbies": "历史与文艺",
                "residence": "北京",
                "gender": "male",
            },
            "dictionary_definition_style": "- 词意\n- 词源",
        }
    }
    setting = dict_to_setting(data)
    assert setting.user_profile.language.interface_language == "zh-CN"
    assert setting.user_profile.language.target_language == "en"
    assert setting.user_profile.background.hobbies == "历史与文艺"
    assert setting.user_profile.background.residence == "北京"
    assert setting.user_profile.background.gender == "male"
    assert setting.user_profile.dictionary_definition_style == "- 词意\n- 词源"
    # 序列化回 dict 结构也应保持一致
    d = setting_to_dict(setting)
    assert d["user_profile"]["language"]["interface_language"] == "zh-CN"
    assert d["user_profile"]["background"]["hobbies"] == "历史与文艺"


# Pydantic 特性：schema 校验与 JSON Schema 生成

def test_log_level_invalid_value_raises():
    # log_level 字段仅允许 debug/info/warn/error，非法值应触发 ValidationError
    with pytest.raises(ValidationError):
        LoggingSetting(log_level="verbose")


def test_log_level_valid_values():
    for level in ("debug", "info", "warn", "error"):
        ls = LoggingSetting(log_level=level)
        assert ls.log_level == level


def test_everlingo_setting_json_schema():
    # EverLingoSetting 可以生成 JSON Schema，ref: configuration.md 配置实现基础选型
    schema = EverLingoSetting.model_json_schema()
    assert schema["type"] == "object"
    assert "properties" in schema
    assert "sys_setting" in schema["properties"]
    assert "user_profile" in schema["properties"]


def test_logging_setting_json_schema_has_field_descriptions():
    schema = LoggingSetting.model_json_schema()
    props = schema["properties"]
    assert "description" in props["log_file"]
    assert "description" in props["log_level"]


def test_sys_setting_json_schema_has_nested_models():
    schema = SysSetting.model_json_schema()
    props = schema["properties"]
    assert "logging_setting" in props
    assert "tracing_setting" in props
