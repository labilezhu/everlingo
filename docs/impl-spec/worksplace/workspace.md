# Workspace

抽象出 workspace 概念。支持同一台服务器安装多个独立配置的 everlingo 实例。

## 原配置文件目录结构需要重构
之前，配置目录 hard code 在 `~/.everlingo/` :
```
.
├── everlingo.yaml
├── logs
│   └── everlingo.log
├── USER.md
```
现在引入 workspace 概念。需要改变。

## 配置文件目录结构

现在引入 workspace 概念。多个 workspace 存放在目录 `~/.everlingo/workspaces` 下：
```
default/
workspace_a/
workspace_b/
```

其中 default 为默认的 workspace。

每个 workspace 的结构如下：
```
/everlingo.yaml
/logs
    everlingo.log
/memory
    USER.md
```

## Workspace 选择机制

代码实现位于 `src/everlingo/workspace.py`。当前 workspace 的解析优先级如下：

1. **CLI 参数 `--workspace` / `-w`**（最高优先级）
   - 仅当 `everlingo` 命令显式传入时生效
   - 调用 `workspace.init_workspace(name)`
2. **环境变量 `EVERLINGO_WORKSPACE`**
   - 在未通过 CLI 显式指定时生效
3. **默认 `"default"`**
   - 两者都未指定时回退

```bash
# 显式指定 workspace
everlingo --workspace workspace_a
everlingo -w workspace_a

# 或通过环境变量
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