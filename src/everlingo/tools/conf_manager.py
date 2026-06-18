from pathlib import Path

import yaml
from langchain_core.tools import tool

from ..setting import dict_to_setting, load_setting, save_setting, setting_to_dict
from . import log_tool_call

# 配置更新计数器。每次 set_config 成功后递增。
# MainAgent 通过比对版本号决定是否重建 agent。
_config_version: int = 0


def get_config_version() -> int:
    """返回当前配置版本号。"""
    return _config_version


@tool("conf_manager_get_schema")
@log_tool_call("conf_manager_get_schema")
def get_schema() -> str:
    """获取配置元信息描述与schema，返回 everlingo.example.yaml 内容"""
    example_path = Path(__file__).parent.parent.parent.parent / "everlingo.example.yaml"
    if example_path.exists():
        return example_path.read_text(encoding="utf-8")
    return ""


@tool("conf_manager_get_config")
@log_tool_call("conf_manager_get_config")
def get_config() -> str:
    """查询当前生效的配置文件内容，返回 YAML 格式"""
    setting = load_setting()
    return yaml.dump(
        setting_to_dict(setting), allow_unicode=True, indent=2, sort_keys=False
    )


@tool("conf_manager_set_config")
@log_tool_call("conf_manager_set_config")
def set_config(config_to_be_merged: str) -> str:
    """修改多个配置项目。参数 configToBeMerged 是 YAML 格式的配置片段，merged 到当前配置后返回完整配置。"""
    current = setting_to_dict(load_setting())
    try:
        merge_data = yaml.safe_load(config_to_be_merged)
    except yaml.YAMLError as e:
        return f"error: YAML 解析失败: {e}"

    if not isinstance(merge_data, dict):
        return "error: 配置必须是 YAML 对象格式"

    def deep_merge(base: dict, override: dict) -> None:
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                deep_merge(base[key], value)
            else:
                base[key] = value

    deep_merge(current, merge_data)
    save_setting(dict_to_setting(current))

    global _config_version
    _config_version += 1

    return yaml.dump(current, allow_unicode=True, indent=2, sort_keys=False)
