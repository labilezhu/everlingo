import logging
import tempfile
from pathlib import Path

import yaml

from everlingo.models import EverLingoSetting, LoggingSetting, SysSetting, UserProfile
from everlingo.setting import get_prompt_version, save_setting
from everlingo.tools.clock import get_datetime
from everlingo.tools.conf_manager import get_config, get_schema, set_config, get_config_version
from everlingo.tools.tools import get_all_tools


def test_clock_logs_tool_call(caplog):
    caplog.set_level(logging.DEBUG, logger="everlingo")
    result = get_datetime.invoke({})
    assert "tool_name: clock_get_datetime" in caplog.text
    assert "parameters: " in caplog.text
    assert "return: " in caplog.text
    assert result in caplog.text


def test_get_schema_logs_tool_call(caplog):
    caplog.set_level(logging.DEBUG, logger="everlingo")
    result = get_schema.invoke({})
    assert "tool_name: conf_manager_get_schema" in caplog.text
    assert "return: " in caplog.text
    assert result in caplog.text


def test_get_config_logs_tool_call(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger="everlingo")
    setting = EverLingoSetting(
        sys_setting=SysSetting(logging_setting=LoggingSetting()),
        user_profile=UserProfile(),
    )
    monkeypatch.setattr("everlingo.tools.conf_manager.load_setting", lambda: setting)
    result = get_config.invoke({})
    assert "tool_name: conf_manager_get_config" in caplog.text
    assert "return: " in caplog.text
    assert result in caplog.text


def test_set_config_logs_tool_call(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger="everlingo")
    setting = EverLingoSetting(
        sys_setting=SysSetting(logging_setting=LoggingSetting()),
        user_profile=UserProfile(),
    )
    monkeypatch.setattr("everlingo.tools.conf_manager.load_setting", lambda: setting)
    monkeypatch.setattr("everlingo.tools.conf_manager.save_setting", lambda s: None)
    result = set_config.invoke({"config_to_be_merged": "user_profile:\n  name: test"})
    assert "tool_name: conf_manager_set_config" in caplog.text
    assert "parameters: config_to_be_merged=user_profile:" in caplog.text
    assert "return: " in caplog.text
    assert "name: test" in result


def test_set_config_increments_version(monkeypatch):
    """set_config 成功后，prompt 版本号应递增。"""
    setting = EverLingoSetting(
        sys_setting=SysSetting(logging_setting=LoggingSetting()),
        user_profile=UserProfile(),
    )
    monkeypatch.setattr("everlingo.tools.conf_manager.load_setting", lambda: setting)
    monkeypatch.setattr("everlingo.tools.conf_manager.save_setting", lambda s: None)

    version_before = get_prompt_version()
    set_config.invoke({"config_to_be_merged": "user_profile:\n  language:\n    target_language: fr"})
    version_after = get_prompt_version()

    assert version_after == version_before + 1


def test_set_config_increments_version_multiple_times(monkeypatch):
    """多次 set_config 每次都应递增版本号。"""
    setting = EverLingoSetting(
        sys_setting=SysSetting(logging_setting=LoggingSetting()),
        user_profile=UserProfile(),
    )
    monkeypatch.setattr("everlingo.tools.conf_manager.load_setting", lambda: setting)
    monkeypatch.setattr("everlingo.tools.conf_manager.save_setting", lambda s: None)

    version_before = get_prompt_version()
    set_config.invoke({"config_to_be_merged": "user_profile:\n  language:\n    target_language: fr"})
    set_config.invoke({"config_to_be_merged": "user_profile:\n  language:\n    target_language: de"})
    version_after = get_prompt_version()

    assert version_after == version_before + 2


def test_set_config_invalid_yaml_does_not_increment_version(monkeypatch):
    """set_config 入参 YAML 无效时，版本号不应递增。"""
    setting = EverLingoSetting(
        sys_setting=SysSetting(logging_setting=LoggingSetting()),
        user_profile=UserProfile(),
    )
    monkeypatch.setattr("everlingo.tools.conf_manager.load_setting", lambda: setting)
    monkeypatch.setattr("everlingo.tools.conf_manager.save_setting", lambda s: None)

    version_before = get_prompt_version()
    result = set_config.invoke({"config_to_be_merged": ": invalid: yaml: ["})
    version_after = get_prompt_version()

    assert version_after == version_before
    assert "error" in result


def test_get_all_tools_returns_tool_objects():
    tools = get_all_tools()
    assert len(tools) == 6
    for t in tools:
        assert hasattr(t, "invoke")
        assert hasattr(t, "name")
    names = [t.name for t in tools]
    assert "clock_get_datetime" in names
    assert "conf_manager_get_schema" in names
    assert "conf_manager_get_config" in names
    assert "conf_manager_set_config" in names
    assert "user_doc_get" in names
    assert "user_doc_set" in names
