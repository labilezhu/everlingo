from pathlib import Path

import yaml

from .models import (
    EverLingoSetting,
    UserProfile,
)

SETTING_PATH = Path.home() / ".everlingo" / "everlingo.yaml"


def dict_to_setting(data: dict) -> EverLingoSetting:
    # ref: configuration.md yaml 结构
    # YAML 结构与模型结构对齐，直接用 model_validate 解析
    return EverLingoSetting.model_validate(data)


def setting_to_dict(setting: EverLingoSetting) -> dict:
    # ref: configuration.md yaml 结构
    return setting.model_dump()


def _load_raw() -> dict:
    if SETTING_PATH.exists():
        with open(SETTING_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    return {}


def _dump_raw(data: dict) -> None:
    SETTING_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTING_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, indent=2, sort_keys=False)


def load_setting() -> EverLingoSetting:
    return dict_to_setting(_load_raw())


def save_setting(setting: EverLingoSetting) -> None:
    _dump_raw(setting_to_dict(setting))


def load_profile() -> UserProfile:
    return load_setting().user_profile


def save_profile(profile: UserProfile) -> None:
    setting = load_setting()
    setting = setting.model_copy(update={"user_profile": profile})
    save_setting(setting)
