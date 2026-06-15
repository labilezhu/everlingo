from everlingo.models import EverLingoSetting, SysSetting, UserProfile


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
