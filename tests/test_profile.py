from everlingo.models import (
    EverLingoSetting,
    LoggingSetting,
    SysSetting,
    TracingSetting,
    UserProfile,
)
from everlingo.profile import dict_to_setting, setting_to_dict


def test_empty_profile_is_incomplete():
    profile = UserProfile()
    assert not profile.is_complete()
    errors = profile.validate()
    assert len(errors) == 2


def test_partial_profile_is_incomplete():
    profile = UserProfile(interface_language="zh-CN")
    assert not profile.is_complete()
    errors = profile.validate()
    assert len(errors) == 1
    assert "目标学习语言" in errors[0]


def test_complete_profile():
    profile = UserProfile(interface_language="zh-CN", target_language="en")
    assert profile.is_complete()
    assert profile.validate() == []


def test_same_languages_not_allowed():
    profile = UserProfile(interface_language="zh-CN", target_language="zh-CN")
    errors = profile.validate()
    assert len(errors) == 1
    assert "不能相同" in errors[0]


def test_profile_with_background():
    profile = UserProfile(
        interface_language="zh-CN",
        target_language="en",
        hobbies="历史与文艺",
        residence="北京",
        gender="male",
        dictionary_definition_style="- 词意\n- 词源",
    )
    assert profile.is_complete()
    assert profile.hobbies == "历史与文艺"
    assert profile.residence == "北京"
    assert profile.gender == "male"
    assert profile.dictionary_definition_style == "- 词意\n- 词源"


def test_sys_setting_defaults():
    ss = SysSetting()
    assert ss.openai_api_key == ""
    assert ss.openai_base_url == ""
    assert ss.openai_model == ""


def test_everlingo_setting_defaults():
    setting = EverLingoSetting()
    assert setting.sys_setting.openai_api_key == ""
    assert setting.user_profile.interface_language == ""


def test_everlingo_setting_full():
    setting = EverLingoSetting(
        sys_setting=SysSetting(
            openai_api_key="sk-test",
            openai_base_url="https://test.api.com",
            openai_model="gpt-4",
        ),
        user_profile=UserProfile(
            interface_language="zh-CN",
            target_language="en",
        ),
    )
    assert setting.sys_setting.openai_api_key == "sk-test"
    assert setting.sys_setting.openai_base_url == "https://test.api.com"
    assert setting.sys_setting.openai_model == "gpt-4"
    assert setting.user_profile.interface_language == "zh-CN"
    assert setting.user_profile.target_language == "en"


def test_logging_setting_defaults():
    ls = LoggingSetting()
    assert ls.log_file == ""
    assert ls.log_level == "debug"


def test_everlingo_setting_with_logging():
    setting = EverLingoSetting(
        logging_setting=LoggingSetting(
            log_file="/tmp/everlingo.log",
            log_level="info",
        ),
    )
    assert setting.logging_setting.log_file == "/tmp/everlingo.log"
    assert setting.logging_setting.log_level == "info"


def test_dict_to_setting_includes_logging():
    data = {
        "logging_setting": {
            "log_file": "/custom/path.log",
            "log_level": "warn",
        },
    }
    setting = dict_to_setting(data)
    assert setting.logging_setting.log_file == "/custom/path.log"
    assert setting.logging_setting.log_level == "warn"


def test_setting_to_dict_includes_logging():
    setting = EverLingoSetting(
        logging_setting=LoggingSetting(
            log_file="/custom/path.log",
            log_level="error",
        ),
    )
    d = setting_to_dict(setting)
    assert d["logging_setting"]["log_file"] == "/custom/path.log"
    assert d["logging_setting"]["log_level"] == "error"


def test_logging_roundtrip():
    original = EverLingoSetting(
        sys_setting=SysSetting(openai_api_key="sk-test"),
        logging_setting=LoggingSetting(log_file="/log/test.log", log_level="info"),
        user_profile=UserProfile(interface_language="zh-CN", target_language="en"),
    )
    d = setting_to_dict(original)
    restored = dict_to_setting(d)
    assert restored.logging_setting.log_file == "/log/test.log"
    assert restored.logging_setting.log_level == "info"


def test_tracing_setting_defaults():
    ts = TracingSetting()
    assert ts.tracing_service == ""
    assert ts.langfuse_secret_key == ""
    assert ts.langfuse_public_key == ""
    assert ts.langfuse_base_url == ""


def test_everlingo_setting_with_tracing():
    setting = EverLingoSetting(
        tracing_setting=TracingSetting(
            tracing_service="langfuse",
            langfuse_secret_key="sk-lf-test",
            langfuse_public_key="pk-lf-test",
            langfuse_base_url="http://localhost:3300",
        ),
    )
    assert setting.tracing_setting.tracing_service == "langfuse"
    assert setting.tracing_setting.langfuse_secret_key == "sk-lf-test"
    assert setting.tracing_setting.langfuse_public_key == "pk-lf-test"
    assert setting.tracing_setting.langfuse_base_url == "http://localhost:3300"


def test_dict_to_setting_includes_tracing():
    data = {
        "tracing_setting": {
            "tracing_service": "langfuse",
            "langfuse_secret_key": "sk-lf-test",
            "langfuse_public_key": "pk-lf-test",
            "langfuse_base_url": "http://localhost:3300",
        },
    }
    setting = dict_to_setting(data)
    assert setting.tracing_setting.tracing_service == "langfuse"
    assert setting.tracing_setting.langfuse_secret_key == "sk-lf-test"
    assert setting.tracing_setting.langfuse_public_key == "pk-lf-test"
    assert setting.tracing_setting.langfuse_base_url == "http://localhost:3300"


def test_setting_to_dict_includes_tracing():
    setting = EverLingoSetting(
        tracing_setting=TracingSetting(
            tracing_service="langfuse",
            langfuse_secret_key="sk-lf-test",
            langfuse_public_key="pk-lf-test",
            langfuse_base_url="http://localhost:3300",
        ),
    )
    d = setting_to_dict(setting)
    assert d["tracing_setting"]["tracing_service"] == "langfuse"
    assert d["tracing_setting"]["langfuse_secret_key"] == "sk-lf-test"
    assert d["tracing_setting"]["langfuse_public_key"] == "pk-lf-test"
    assert d["tracing_setting"]["langfuse_base_url"] == "http://localhost:3300"


def test_tracing_roundtrip():
    original = EverLingoSetting(
        tracing_setting=TracingSetting(
            tracing_service="langfuse",
            langfuse_secret_key="sk-lf-test",
            langfuse_public_key="pk-lf-test",
            langfuse_base_url="http://localhost:3300",
        ),
    )
    d = setting_to_dict(original)
    restored = dict_to_setting(d)
    assert restored.tracing_setting.tracing_service == "langfuse"
    assert restored.tracing_setting.langfuse_secret_key == "sk-lf-test"
    assert restored.tracing_setting.langfuse_public_key == "pk-lf-test"
    assert restored.tracing_setting.langfuse_base_url == "http://localhost:3300"
