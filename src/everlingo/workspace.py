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

# 进程级当前 workspace 目录。
# 非空时优先于 _current_ws_name 解析：current_workspace() 直接返回该路径，
# 不再拼接 WORKSPACE_ROOT/<name>。用于把 workspace 指向任意目录。
# ref: docs/impl-spec/worksplace/workspace.md — 选择机制
_current_ws_dir: Path | None = None


def init_workspace(name: str | None) -> None:
    """显式设定当前 workspace（按名字）。

    - 传入非空字符串：覆盖后续访问器的路径解析结果（若未同时 init dir）
    - 传入 None：重置为"未指定"，让 current_workspace 走 env/default 分支
    - 允许重复调用，后调用覆盖前者（便于测试切换 workspace）

    ref: docs/impl-spec/worksplace/workspace.md — 选择机制
    """
    global _current_ws_name
    _current_ws_name = name


def init_workspace_dir(path: str | Path | None) -> None:
    """显式设定当前 workspace 目录（任意路径）。

    - 传入非空路径：覆盖后续访问器路径解析，current_workspace() 直接返回该路径
    - 传入 None：重置为"未指定"，让 current_workspace 走 env/default 分支
    - 路径仅做 expanduser() 处理，不做 resolve()，由调用方负责创建
    - 优先级高于 init_workspace() 与所有 name-based 来源

    ref: docs/impl-spec/worksplace/workspace.md — 选择机制
    """
    global _current_ws_dir
    _current_ws_dir = Path(path).expanduser() if path is not None else None


def _resolve_ws_name() -> str:
    """按优先级解析 workspace 名：init > env > 'default'."""
    if _current_ws_name is not None:
        return _current_ws_name
    return os.getenv("EVERLINGO_WORKSPACE") or "default"


def _resolve_ws_dir() -> Path | None:
    """解析来自环境变量的 workspace 目录；未设置返回 None."""
    raw = os.getenv("EVERLINGO_WORKSPACE_DIR")
    if raw is None or raw == "":
        return None
    return Path(raw).expanduser()


def current_workspace() -> Path:
    """返回当前 workspace 根目录路径。

    解析优先级：init dir > EVERLINGO_WORKSPACE_DIR > init name > env name > 'default'.

    不负责创建目录；调用方在需要时自行 mkdir(parents=True)。
    """
    if _current_ws_dir is not None:
        return _current_ws_dir
    dir_from_env = _resolve_ws_dir()
    if dir_from_env is not None:
        return dir_from_env
    return WORKSPACE_ROOT / _resolve_ws_name()


def setting_path() -> Path:
    """返回当前 workspace 的 everlingo.yaml 路径。"""
    return current_workspace() / "everlingo.yaml"


def memory_dir() -> Path:
    """返回当前 workspace 的 memory 目录路径（USER.md 的存放位置）。"""
    return current_workspace() / "memory"


def vault_dir() -> Path:
    """返回当前 workspace 的 Memory Vault 文件目录路径（$ws/memory/vault）。"""
    return current_workspace() / "memory" / "vault"


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


def index_dir() -> Path:
    """返回当前 workspace 的 search index 目录路径。

    ref: docs/impl-spec/search/memory-vault-search-spec.md — DB 文件位置
    包含 memory.sqlite（SQLite+FTS5 索引）与 indexer.sock（IPC unix socket）。
    不负责创建；调用方在需要时自行 mkdir(parents=True)。
    """
    return current_workspace() / "memory" / "vault_index"


def index_db_path() -> Path:
    """返回 SQLite DB 文件路径 ($workspace/memory/vault_index/memory.sqlite)。"""
    return index_dir() / "memory.sqlite"


def indexer_socket_path() -> Path:
    """返回 indexer IPC unix socket 路径 ($workspace/memory/vault_index/indexer.sock)。"""
    return index_dir() / "indexer.sock"
