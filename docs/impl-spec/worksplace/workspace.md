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
indexer.mcp.url      # indexer 启动时写入的 MCP Streamable HTTP URL，供 MCP 客户端连接（见 valut-mcp-spec.md「部署形态」）

/memory # Memory Spec
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
            tmp/ # 程序内部临时文件，无用户数据价值，watcher 不索引

      ja/ # 目标学习语言  
```

变化概述：每个语言独立一个 vault，独立一个 sqlite db 。但共享 indexer 进程 和 indexer.sock 文件。这样可以实现全文搜索的语言隔离（避免跨语言词项污染与 BM25 排名偏置），并为将来按语言选型 schema / embedding 模型留出空间。共享 indexer 进程 + 单 socket 仍保持「gateway 不碰 SQLite、单写者」核心约束不变。


#### Memory Spec
见 [Memory Spec](docs/impl-spec/worksplace/memory-vault-spec.md) .


### 下游影响

本次重构涉及搜索子系统多份 spec 的协同更新（仅 spec 文档变更，代码改动另议）：

- **schema**：`documents.lang` 列与 `idx_doc_lang_type` 索引删除——lang 已隐含于 DB，不再作为列存储。`SearchHit.lang` 字段仍保留（indexer 按 DB 语言回填，protocol 对外不变）。
- **file_path**：`documents.file_path` 的 base 由「相对 `$workspace/memory/vault`」改为「相对该语言 vault 根 `$workspace/memory/languages/$lang/vault`」，前缀 `{lang}/` 消失。
- **watcher**：监听根由单个 `$workspace/memory/vault/` 变为 N 个 `$workspace/memory/languages/*/vault/`，每个 lang vault 各起一个 watcher。
- **reconcile**：indexer 启动时枚举 `$workspace/memory/languages/*/` 确定语言集合，对每个 lang vault 分别全量对账。无 lang 目录时为空 vault，indexer 仍可启动。**运行时新 lang 发现**：indexer 启动后还会用 lang 发现 watcher（监听 `$workspace/memory/languages/`，recursive）监测新 `*/vault/` 目录出现，并走与启动时相同的 `open_lang` 流程（开 DB + reconcile + per-lang watcher）。`POST /{lang}/index` 等端点在 miss 时也走同一懒加载路径（vault 目录存在为前提）。两条路径共享 `AppState._open_lang()` 同一加锁入口；vault 目录从未创建过的 lang 端点返回 404 `lang not found`。详见 [memory-vault-search-spec.md](/docs/impl-spec/search/memory-vault-search-spec.md)「运行时新 lang 发现」节。
- **HTTP 协议**：所有端点增加 `lang` 路由维度（path segment `/{lang}/...`）。`POST /search` 的 `lang` 字段改为必填（不再支持 `lang=None` 跨语言检索；API 返回错误）。详见 [search-api-spec.md](/docs/impl-spec/search/search-api-spec.md)。
- **EmbeddingWorker**：改为单 worker 轮询 N 个 lang DB 的 pending chunks，按 lang 分批调 embedder。各 lang DB 的 `meta.embedding_model_id` 可不同。详见 [memory-vault-embedding-spec.md](/docs/impl-spec/search/memory-vault-embedding-spec.md)。
- **进程拓扑**：indexer 进程持有 N 个 SQLite RW 连接（每 lang 一个）+ 一个 workspace 级 socket。详见 [memory-vault-search-spec.md](/docs/impl-spec/search/memory-vault-search-spec.md)「进程拓扑」。


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
