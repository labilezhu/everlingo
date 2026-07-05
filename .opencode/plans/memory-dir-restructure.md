# Plan: Memory Vault 目录结构调整

## Context

当前 `$workspace/memory` 既是 USER.md 的存放目录，也是 Memory Vault 文件的根目录；`$workspace/index` 存放搜索索引。

新结构（见 `docs/impl-spec/worksplace/workspace.md` § Workspace 目录结构）：
- `$ws/memory/USER.md` — 不变
- `$ws/memory/vault/` — Memory Vault 文件（原 `$ws/memory/*`）
- `$ws/memory/vault_index/` — 搜索索引（原 `$ws/index/`）

---

## 变更明细

### 1. `src/everlingo/workspace.py` — 访问器调整

- 新增 `vault_dir() -> Path`：返回 `$ws/memory/vault`
- `index_dir()` 返回值改为 `current_workspace() / "memory" / "vault_index"`（函数名保留）
- `memory_dir()` / `user_doc_path()` 不变
- 更新 `index_dir()` / `index_db_path()` / `indexer_socket_path()` 的 docstring 路径示例

### 2. Vault 文件操作改用 `vault_dir()`

| 文件 | 行号 | 改动 |
|------|------|------|
| `src/everlingo/mem/agents/mem_writer_tools.py` | ~87 | `_memory_root()` 返回 `workspace.vault_dir().resolve()` |
| `src/everlingo/mem/agents/mem_writer_agent.py` | ~236 | `abs_path = (workspace.memory_dir() / rel).resolve()` → `workspace.vault_dir() / rel` |
| `src/everlingo/mem/vault/search/cli.py` | ~137 | `memory_root = workspace.memory_dir()` → `workspace.vault_dir()` |
| `src/everlingo/mem/vault/search/server.py` | ~321 | 同上 |

### 3. 注释 / 文案更新

| 文件 | 改动 |
|------|------|
| `src/everlingo/mem/vault/search/watcher.py` | 头注释 `$workspace/memory/` → `$workspace/memory/vault/` |
| `src/everlingo/mem/vault/search/server.py` | 头注释同上 |
| `src/everlingo/mem/agents/mem_writer_agent.py` | system prompt 文案 `$workspace/memory/` → `$workspace/memory/vault/` |
| `src/everlingo/main.py` | argparse 帮助文案 `相对 $workspace/memory` → `相对 $workspace/memory/vault` |

### 4. 文档更新

| 文件 | 改动 |
|------|------|
| `src/everlingo/mem/vault/vault_spec.md` | vault 根路径 `$workspace/memory/` → `$workspace/memory/vault/` |
| `docs/impl-spec/search/memory-vault-search-spec.md` | DB 路径、监听根、IPC socket 路径 |
| `docs/impl-spec/search/search-api-spec.md` | curl 示例 `$workspace/index/indexer.sock` → `$workspace/memory/vault_index/indexer.sock` |
| `docs/impl-spec/memory-writer-agent-spec.md` | 相对路径根说明、`memory_dir()` → `vault_dir()` |

### 5. 测试更新

| 文件 | 改动 |
|------|------|
| `tests/test_workspace_index.py` | 断言 `index_dir() == tmp_path / "memory" / "vault_index"` |
| `tests/test_workspace.py` | 新增 `test_vault_dir_under_memory_dir`、`test_index_dir_under_memory_dir`；已有测试追加 vault_dir / index_dir 断言 |
| `tests/test_setting.py` | 更新行 ~437 注释 |
| `tests/test_mem_writer_agent.py` | 更新行 ~53 注释 |

### 6. `TASKS.md` 记录

追加本次结构调整的完成记录。

---

## 验证

```bash
pytest tests/test_workspace.py tests/test_workspace_index.py tests/test_mem_writer_agent.py tests/test_setting.py -v
ruff check src/everlingo tests
```
