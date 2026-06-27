import os
from pathlib import Path

# ref: docs/impl-spec/worksplace/workspace.md — workspace 概念
# 每个 workspace 是 ~/.everlingo/workspaces/<name>/ 下的独立配置实例。
# 该模块自包含 workspace 选择与路径解析，入口模块无需显式初始化。

WORKSPACE_ROOT: Path = Path.home() / ".everlingo" / "workspaces"

# 进程级当前 workspace 名。
# None 表示"未通过 init_workspace 显式指定"，回退到环境变量与默认值。
# 任何 entry point 都可以访问 workspace.current_workspace() 等访问器，
# 不需要在启动时显式调用 init_workspace。
_current_ws_name: str | None = None


def init_workspace(name: str | None) -> None:
    """显式设定当前 workspace。

    - 传入非空字符串：覆盖后续访问器的路径解析结果
    - 传入 None：重置为"未指定"，让 current_workspace 走 env/default 分支
    - 允许重复调用，后调用覆盖前者（便于测试切换 workspace）

    ref: docs/impl-spec/worksplace/workspace.md — 选择机制
    """
    global _current_ws_name
    _current_ws_name = name


def _resolve_ws_name() -> str:
    """按优先级解析 workspace 名：init > env > 'default'."""
    if _current_ws_name is not None:
        return _current_ws_name
    return os.getenv("EVERLINGO_WORKSPACE") or "default"


def current_workspace() -> Path:
    """返回当前 workspace 根目录路径。

    不负责创建目录；调用方在需要时自行 mkdir(parents=True)。
    """
    return WORKSPACE_ROOT / _resolve_ws_name()


def setting_path() -> Path:
    """返回当前 workspace 的 everlingo.yaml 路径。"""
    return current_workspace() / "everlingo.yaml"


def memory_dir() -> Path:
    """返回当前 workspace 的 memory 目录路径（USER.md 的存放位置）。"""
    return current_workspace() / "memory"


def user_doc_path() -> Path:
    """返回当前 workspace 的 USER.md 路径（自由文本偏好笔记）。"""
    return memory_dir() / "USER.md"


def log_path() -> Path:
    """返回当前 workspace 的默认日志文件路径。"""
    return current_workspace() / "logs" / "everlingo.log"


def plugins_dir() -> Path:
    """返回当前 workspace 的 plugins 目录路径。

    ref: docs/impl-spec/channel-wechat-ilink.md — $workspace/plugins/channels/<channel>/...
    通用插件根目录；各插件自行拼装子路径。
    """
    return current_workspace() / "plugins"