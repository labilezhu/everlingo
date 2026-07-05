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

当前实现，每个 workspace 的结构示例如下：
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
    /vault_index
       memory.sqlite
       indexer.sock
    /vault
      en/ # 目标学习语言
         events/
            2026/
               06/
               2026-06-26.md
         items/ # 知识点类 memory items
            vocab/
               gcc--01JZABC123.md
               ambiguous--01JZABC456.md
            phrase/
               take-for-granted--01JZABC789.md
            grammar/
               present-perfect--01JZABD001.md
            pragmatics/ # 语用
            others/ # 其它分类

      ja/ # 目标学习语言
         events/
            2026/
               06/
               2026-06-26.md
         items/ # 知识点类 memory items
            vocab/
               aimai--01JZABD123.md
         ...

      tmp/ #程序内容使用的临时文件，没有用户数据价值。

    /vault_index 
```

现在要重构 workspace 的目录结构示例如下：
```bash
/everlingo.yaml
/logs
    everlingo.log
    indexer.log

/plugins
   channels/
      wechat_channel/
         credentials/

indexer.sock

/memory
    USER.md
    languages/
      en/ # 目标学习语言
         index/
            memory.sqlite
         vault/
            events/
               2026/
                  06/
                  2026-06-26.md
            items/ # 知识点类 memory items
               vocab/
                  gcc--01JZABC123.md
                  ambiguous--01JZABC456.md
               phrase/
                  take-for-granted--01JZABC789.md
               grammar/
                  present-perfect--01JZABD001.md
               pragmatics/ # 语用
               others/ # 其它分类

      ja/ # 目标学习语言  
```
变化概述：每个语言独立一个 vault，独立一个 sqlite db 。但共享 indexer 进程 和 indexer.sock 文件。处理是本文搜索和语义搜索可以避免多语言互相影响。 将来，vault 的 schema 也可以不同。
变化列表： 
- vault 的位置： $workspace/memory/vault -> $workspace/memory/languages/$lang/vault 。 每个语言独立一个 vault
- memory.sqlite 位置: $workspace/memory/vault_index/memory.sqlite ->  $workspace/memory/languages/$lang/index/memory.sqlite。 每个语言独立一个 sqlite db
- indexer.sock 位置： workspace/memory/vault_index/indexer.sock -> $workspace/indexer.sock

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