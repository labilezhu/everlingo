from everlingo.models import UserProfile


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
