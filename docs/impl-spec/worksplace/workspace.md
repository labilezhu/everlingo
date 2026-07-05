# Workspace

抽象出 workspace 概念。支持同一台服务器安装多个独立配置的 everlingo 实例。

## EverLingo 目录结构

现在引入 workspace 概念。多个 workspace 存放在目录 `~/.everlingo/workspaces` 下：
```
default/
workspace_a/
workspace_b/
```

其中 default 为默认的 workspace。

### Workspace 目录结构

每个 workspace 的结构示例如下：
```bash
/everlingo.yaml
/logs
    everlingo.log
    indexer.log

/plugins
   /channels
      /wechat_channel
         /credentials  
/memory
    USER.md
    /vault
    /vault_index 
```

## Workspace 选择机制

代码实现位于 `src/everlingo/workspace.py`。当前 workspace 的解析优先级如下：

1. **CLI 参数 `--workspace-dir <path>`**（最高优先级）
   - 仅当 `everlingo` 命令显式传入时生效
   - 调用 `workspace.init_workspace_dir(path)`，直接将该路径作为 workspace 根目录
   - 路径仅做 `expanduser()` 处理，不做 `resolve()`（不存在目录也允许，调用方负责创建）
2. **环境变量 `EVERLINGO_WORKSPACE_DIR`**
   - 在未通过 CLI 显式指定 dir 时生效
3. **CLI 参数 `--workspace` / `-w`**
   - 与 `--workspace-dir` 互斥（同时指定时 argparse 报错退出）
   - 调用 `workspace.init_workspace(name)`，name 拼接到 `WORKSPACE_ROOT` 下
4. **环境变量 `EVERLINGO_WORKSPACE`**
   - 在未通过 CLI 显式指定 name 时生效
5. **默认 `"default"`**
   - 全部未指定时回退到 `~/.everlingo/workspaces/default/`

```bash
# 指定任意目录作为 workspace
everlingo --workspace-dir /path/to/my_ws
EVERLINGO_WORKSPACE_DIR=/path/to/my_ws everlingo

# 或指定 ~/.everlingo/workspaces/ 下的名字
everlingo --workspace workspace_a
everlingo -w workspace_a
EVERLINGO_WORKSPACE=workspace_b everlingo
```

入口模块（`main.py`、`gateway.py` 等）不需要显式初始化 workspace —— 直接访问 `workspace.current_workspace()` / `workspace.setting_path()` 等访问器即可，由模块自身按上述优先级解析。

## 旧布局兼容

本次重构**不**自动迁移旧的扁平布局 `~/.everlingo/{everlingo.yaml, USER.md, logs/}`。升级用户需要手动把旧文件移动到 `~/.everlingo/workspaces/default/` 下：

```
~/.everlingo/everlingo.yaml → ~/.everlingo/workspaces/default/everlingo.yaml
~/.everlingo/USER.md        → ~/.everlingo/workspaces/default/memory/USER.md
~/.everlingo/logs/          → ~/.everlingo/workspaces/default/logs/
```