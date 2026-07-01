import importlib
from pathlib import Path

import pytest

from everlingo import workspace


@pytest.fixture(autouse=True)
def reset_workspace_state(monkeypatch):
    """每个测试前后重置 workspace 模块状态与 EVERLINGO_WORKSPACE* 环境变量。"""
    monkeypatch.delenv("EVERLINGO_WORKSPACE", raising=False)
    monkeypatch.delenv("EVERLINGO_WORKSPACE_DIR", raising=False)
    importlib.reload(workspace)
    yield
    importlib.reload(workspace)


def test_default_workspace_when_no_override(reset_workspace_state):
    """未指定 workspace 时，current_workspace 应回退到 default。"""
    ws = workspace.current_workspace()
    assert ws == workspace.WORKSPACE_ROOT / "default"


def test_init_workspace_overrides_default(reset_workspace_state):
    """显式 init_workspace 后，current_workspace 应使用 init 的名字。"""
    workspace.init_workspace("alpha")
    ws = workspace.current_workspace()
    assert ws == workspace.WORKSPACE_ROOT / "alpha"


def test_init_overrides_env(reset_workspace_state, monkeypatch):
    """init_workspace 应优先于 EVERLINGO_WORKSPACE 环境变量。"""
    monkeypatch.setenv("EVERLINGO_WORKSPACE", "from_env")
    workspace.init_workspace("from_init")
    assert workspace.current_workspace().name == "from_init"


def test_env_overrides_default(reset_workspace_state, monkeypatch):
    """未 init 时，EVERLINGO_WORKSPACE 环境变量应优先于 default。"""
    monkeypatch.setenv("EVERLINGO_WORKSPACE", "from_env")
    ws = workspace.current_workspace()
    assert ws == workspace.WORKSPACE_ROOT / "from_env"


def test_init_workspace_none_resets(reset_workspace_state, monkeypatch):
    """init_workspace(None) 应重置为"未指定"，让 env/default 重新生效。"""
    monkeypatch.setenv("EVERLINGO_WORKSPACE", "from_env")
    workspace.init_workspace("first")
    assert workspace.current_workspace().name == "first"

    workspace.init_workspace(None)
    assert workspace.current_workspace().name == "from_env"

    monkeypatch.delenv("EVERLINGO_WORKSPACE")
    assert workspace.current_workspace().name == "default"


def test_init_workspace_can_be_overridden(reset_workspace_state):
    """init_workspace 允许重复调用，后调用覆盖前者。"""
    workspace.init_workspace("first")
    workspace.init_workspace("second")
    assert workspace.current_workspace().name == "second"


def test_setting_path_under_current_workspace(reset_workspace_state):
    """setting_path 应位于 current_workspace 下，文件名为 everlingo.yaml。"""
    workspace.init_workspace("ws_a")
    assert workspace.setting_path() == workspace.WORKSPACE_ROOT / "ws_a" / "everlingo.yaml"


def test_user_doc_path_under_memory_dir(reset_workspace_state):
    """user_doc_path 应位于 $ws/memory/USER.md。"""
    workspace.init_workspace("ws_b")
    assert workspace.user_doc_path() == workspace.WORKSPACE_ROOT / "ws_b" / "memory" / "USER.md"


def test_log_path_under_current_workspace(reset_workspace_state):
    """log_path 应位于 $ws/logs/everlingo.log。"""
    workspace.init_workspace("ws_c")
    assert workspace.log_path() == workspace.WORKSPACE_ROOT / "ws_c" / "logs" / "everlingo.log"


def test_plugins_dir_under_current_workspace(reset_workspace_state):
    """plugins_dir 应位于 $ws/plugins。"""
    workspace.init_workspace("ws_plugins")
    assert workspace.plugins_dir() == workspace.WORKSPACE_ROOT / "ws_plugins" / "plugins"


def test_accessors_follow_init_changes(reset_workspace_state):
    """init_workspace 切换 workspace 后，访问器应返回新 workspace 下的路径。"""
    workspace.init_workspace("ws_x")
    assert workspace.setting_path().parent.name == "ws_x"

    workspace.init_workspace("ws_y")
    assert workspace.setting_path().parent.name == "ws_y"
    assert workspace.user_doc_path().parent.parent.name == "ws_y"
    assert workspace.log_path().parent.parent.name == "ws_y"


def test_init_workspace_dir_overrides_name(reset_workspace_state):
    """init_workspace_dir 应优先于 init_workspace。"""
    workspace.init_workspace("alpha")
    workspace.init_workspace_dir("/tmp/anywhere")
    assert workspace.current_workspace() == Path("/tmp/anywhere")


def test_env_workspace_dir_overrides_env_name(reset_workspace_state, monkeypatch):
    """EVERLINGO_WORKSPACE_DIR 应优先于 EVERLINGO_WORKSPACE。"""
    monkeypatch.setenv("EVERLINGO_WORKSPACE", "from_env_name")
    monkeypatch.setenv("EVERLINGO_WORKSPACE_DIR", "/tmp/from_env_dir")
    assert workspace.current_workspace() == Path("/tmp/from_env_dir")


def test_init_workspace_dir_none_resets(reset_workspace_state, monkeypatch):
    """init_workspace_dir(None) 应重置为"未指定"，让 env/default 重新生效。"""
    monkeypatch.setenv("EVERLINGO_WORKSPACE_DIR", "/tmp/from_env_dir")
    workspace.init_workspace_dir("/tmp/inited")
    assert workspace.current_workspace() == Path("/tmp/inited")

    workspace.init_workspace_dir(None)
    assert workspace.current_workspace() == Path("/tmp/from_env_dir")

    monkeypatch.delenv("EVERLINGO_WORKSPACE_DIR")
    assert workspace.current_workspace() == workspace.WORKSPACE_ROOT / "default"


def test_init_workspace_dir_expands_user(reset_workspace_state):
    """init_workspace_dir 应展开 ~。"""
    workspace.init_workspace_dir("~/my_ws")
    assert workspace.current_workspace() == Path.home() / "my_ws"


def test_init_dir_overrides_env_dir(reset_workspace_state, monkeypatch):
    """init_workspace_dir 应优先于 EVERLINGO_WORKSPACE_DIR。"""
    monkeypatch.setenv("EVERLINGO_WORKSPACE_DIR", "/tmp/from_env_dir")
    workspace.init_workspace_dir("/tmp/inited")
    assert workspace.current_workspace() == Path("/tmp/inited")


def test_accessors_follow_init_dir(reset_workspace_state):
    """init_workspace_dir 设定后，访问器应直接基于该目录。"""
    workspace.init_workspace_dir("/tmp/my_ws")
    assert workspace.setting_path() == Path("/tmp/my_ws/everlingo.yaml")
    assert workspace.user_doc_path() == Path("/tmp/my_ws/memory/USER.md")
    assert workspace.log_path() == Path("/tmp/my_ws/logs/everlingo.log")
    assert workspace.plugins_dir() == Path("/tmp/my_ws/plugins")