import re
from pathlib import Path

import yaml

from . import workspace
from .models import (
    EverLingoSetting,
    UserProfile,
    WebListener,
)
from .utils.yaml_env import expand_env_vars

# ref: docs/impl-spec/worksplace/workspace.md — workspace 概念
# 配置/USER.md 路径不再 hard code 到 ~/.everlingo 根目录，而是
# 由 workspace 模块解析当前 workspace 的根目录。
# 访问 workspace.setting_path() / workspace.user_doc_path() 获取当前 workspace 下的路径。

# Prompt 版本计数器。set_config / user_doc_set 成功后递增。
# MainAgent 通过比对版本号 + 文件 mtime 决定是否重建 agent（刷新 system prompt）。
_prompt_version: int = 0


def get_prompt_version() -> int:
    """返回当前 prompt 版本号。ref: chat-agent-spec.md — system prompt 维护"""
    return _prompt_version


def bump_prompt_version() -> None:
    """递增 prompt 版本号，触发 MainAgent 下次 invoke 时重建 agent。"""
    global _prompt_version
    _prompt_version += 1


def dict_to_setting(data: dict) -> EverLingoSetting:
    # ref: configuration.md yaml 结构
    # YAML 结构与模型结构对齐，直接用 model_validate 解析
    return EverLingoSetting.model_validate(data)


def setting_to_dict(setting: EverLingoSetting) -> dict:
    # ref: configuration.md yaml 结构
    return setting.model_dump()


def _load_raw() -> dict:
    path = workspace.setting_path()
    if path.exists():
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        data = expand_env_vars(data) if isinstance(data, dict) else {}
        return data
    return {}


def _dump_raw(data: dict) -> None:
    path = workspace.setting_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
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


def load_user_doc() -> str:
    """读取 USER.md 自由文本偏好。文件不存在时返回空串。

    ref: DOMAIN.md — 用户自由偏好笔记 (USER.md)
    """
    path = workspace.user_doc_path()
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def save_user_doc(content: str) -> None:
    """写入 USER.md 自由文本偏好。不负责备份（备份由 tool 层处理）。"""
    path = workspace.user_doc_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def prompt_input_mtime() -> float:
    """返回构建 system prompt 所依赖的两个文件的最新 mtime。

    MainAgent 用此值与版本号一起判断是否需要重建 agent，
    使外部编辑器修改 everlingo.yaml / USER.md 也能即时生效。

    ref: chat-agent-spec.md — system prompt 维护
    """
    mtimes: list[float] = []
    setting_path = workspace.setting_path()
    user_doc_path = workspace.user_doc_path()
    if setting_path.exists():
        mtimes.append(setting_path.stat().st_mtime)
    if user_doc_path.exists():
        mtimes.append(user_doc_path.stat().st_mtime)
    return max(mtimes) if mtimes else 0.0


def get_web_listener() -> WebListener:
    """返回 Web Session Acceptor 的生效监听配置。"""
    setting = load_setting()
    return setting.plugins.channels.channel_web.listener


def channel_enabled(channel_name: str) -> bool:
    """返回 channel 是否启用（gateway 无参 config-driven 多 channel 用）。

    语义：`plugins.channels` 下节点存在且 `enable != false` → 启用。
    节点不存在，或节点内 `enable` 显式为 false → 不启用。空节点（如
    `channel_wechat:`）默认启用。

    ref: docs/impl-spec/workspace-console/ws-console-arch.md §4.2 acceptor 选择规则
    """
    data = _load_raw()
    node = data.get("plugins", {}).get("channels", {}).get(channel_name)
    if node is None:
        return False
    if isinstance(node, dict) and node.get("enable") is False:
        return False
    return True


def _validate_base_url(url: str, source: str) -> str:
    """Check base_url starts with http:// or https:// and remove trailing slash."""
    url = url.strip().rstrip("/")
    if not re.match(r"^https?://", url):
        raise ValueError(
            f"public_address.base_url from {source} must start with http:// or https://, "
            f"got: {url!r}"
        )
    return url


def get_web_public_base_url() -> str:
    """返回 Web 前端浏览器访问地址。

    优先级：
    1. 配置的 public_address.base_url（everlingo.yaml）
    2. 环境变量 EVERLINGO_PUBLIC_BASE_URL（多用户拓扑下由 WS-Master 注入）
    3. listener 生效配置自动生成：http://{interface}:{port}

    ref: docs/impl-spec/web-session-acceptor.md — public_address
    ref: docs/impl-spec/multiple-users/ws-master.md — public_base_url 透传
    """
    import os

    setting = load_setting()
    web = setting.plugins.channels.channel_web
    if web.public_address.base_url.strip():
        return _validate_base_url(web.public_address.base_url, "everlingo.yaml")
    env = os.getenv("EVERLINGO_PUBLIC_BASE_URL", "")
    if env.strip():
        return _validate_base_url(env, "env EVERLINGO_PUBLIC_BASE_URL")
    listener = web.listener
    return f"http://{listener.interface}:{listener.port}"