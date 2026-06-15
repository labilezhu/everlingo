from pathlib import Path

import yaml

from .models import (
    EverLingoSetting,
    SysSetting,
    UserProfile,
)

PROFILE_PATH = Path.home() / ".everlingo" / "everlingo.yaml"


def dict_to_setting(data: dict) -> EverLingoSetting:
    ss = data.get("sys_setting", {})
    up = data.get("user_profile", {})
    lang = up.get("language", {})
    bg = up.get("background", {})
    return EverLingoSetting(
        sys_setting=SysSetting(
            openai_api_key=ss.get("openai_api_key", ""),
            openai_base_url=ss.get("openai_base_url", ""),
            openai_model=ss.get("openai_model", ""),
        ),
        user_profile=UserProfile(
            interface_language=lang.get("interface_language", ""),
            target_language=lang.get("target_language", ""),
            hobbies=bg.get("hobbies", ""),
            residence=bg.get("residence", ""),
            gender=bg.get("gender", ""),
            dictionary_definition_style=up.get("dictionary_definition_style", ""),
        ),
    )


def setting_to_dict(setting: EverLingoSetting) -> dict:
    return {
        "sys_setting": {
            "openai_api_key": setting.sys_setting.openai_api_key,
            "openai_base_url": setting.sys_setting.openai_base_url,
            "openai_model": setting.sys_setting.openai_model,
        },
        "user_profile": {
            "language": {
                "interface_language": setting.user_profile.interface_language,
                "target_language": setting.user_profile.target_language,
            },
            "background": {
                "hobbies": setting.user_profile.hobbies,
                "residence": setting.user_profile.residence,
                "gender": setting.user_profile.gender,
            },
            "dictionary_definition_style": setting.user_profile.dictionary_definition_style,
        },
    }


def _load_raw() -> dict:
    if PROFILE_PATH.exists():
        with open(PROFILE_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    return {}


def _dump_raw(data: dict) -> None:
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, indent=2, sort_keys=False)


def load_setting() -> EverLingoSetting:
    return dict_to_setting(_load_raw())


def save_setting(setting: EverLingoSetting) -> None:
    _dump_raw(setting_to_dict(setting))


def load_profile() -> UserProfile:
    return load_setting().user_profile


def save_profile(profile: UserProfile) -> None:
    setting = load_setting()
    setting.user_profile = profile
    save_setting(setting)
