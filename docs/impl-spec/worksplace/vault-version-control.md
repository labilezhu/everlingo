# Memory Vault 版本控制与远端备份

> 关联 ADR：docs/ADR/20260810-vault-version-control.md
> 涉及目录：docs/impl-spec/worksplace/memory-vault-spec.md、workspace.md、workspace-console/

为 [Memory Vault](/docs/impl-spec/worksplace/memory-vault-spec.md) 提供**版本管理**（本地 git 历史）与**远端备份**（git push 到用户自己的 git remote）。目标：误删可回溯、异机可恢复；不引入对 GitHub 的强绑定。

## 1. 总体设计

- `$workspace/memory` 是一整个 git repo（不是整个 workspace）。
- 所有 git 操作（commit / push / pull / rebase / restore）在 **ws-container 内部**完成，ws-master 不参与。
- committer 跑在 **indexer 进程**内（single-writer、已常驻监听文件变更）。
- 远端交互走 **`git` CLI**（非 GitHub Contents API），支持 fetch/pull/rebase。

### 配置（everlingo.yaml 的 git_backup 段）

```yaml
git_backup:
  enabled: false                       # 是否启用自动 commit + 自动 push
  remote_url: ""                       # 任意 git remote，如 git@github.com:user/vault.git
  branch: "main"                       # 上游分支
  auth:
    method: "ssh"                      # ssh | https_pat | https_none
    ssh_private_key_file: ""           # ssh 模式：空=系统 ~/.ssh/；非空=该路径私钥文件
    pat: ""                            # https_pat 模式：GitHub fine-grained PAT（contents:write）
  commit_interval: 300                 # 自动 commit 去抖秒（文件变更后多久聚合一次 commit）
  push_interval: 300                    # 自动 push 间隔秒；0=仅手动触发
```

- 配置读取：`setting.load_git_backup()` / `save_git_backup()`（范式同 `load_profile` / `save_profile`）。
- 多用户部署：ws-master 用 template 初始化（`enabled: false`），用户在 ws-container 内经 console UI / CLI 写入（同 `save_profile`）。
- 凭证保护：依赖 `everlingo.yaml` 文件 0600 权限；不使用 keychain（容器内不可用）。

## 2. git repo 管理

### 2.1 初始化（懒加载）
- 首次 everlingo 启动（indexer lifespan）若 `$workspace/memory/.git` 不存在则 `git init`。
- init 后立即写 `.gitignore`（见 §2.3）并做 **initial commit** 捕获已有 vault 内容。
- repo-local 身份：`user.name=everlingo` / `user.email=noreply@everlingo.local`（不依赖用户全局 git 配置）。
- 启动探测 `git --version`：缺失时 `enabled` 强制 false + log warning，不阻塞主流程。

### 2.2 gitignore
落盘到 `$workspace/memory/.gitignore`：
```
# 语言索引 DB（程序派生，可 reindex --rebuild 重建）
languages/*/index/

# 程序内部临时文件（无用户数据价值，watcher 不索引）
**/vault/tmp/

# 历史遗留备份（USER.md.bak 机制已停）
*.bak
```

### 2.3 远程与分支
- `enabled=true` 且 `remote_url` 非空时，首次 push 前若未配置 `origin` 则 `git remote add origin <remote_url>`。
- 默认 upstream 分支 `main`（可由 `branch` 配置）。

## 3. Committer（indexer 进程内）

### 3.1 设计
- 不订阅 watcher 事件，独立定时器：每 `commit_interval` 秒（或更短轮询）跑 `git status --porcelain`，有 dirty 才 commit。
- commit message：`chore(vault): auto-snapshot <ISO8601>`。
- commit 后若 `enabled=true` 且 `remote_url` 非空且距上次 push ≥ `push_interval`，自动 `git push --force-with-lease origin <branch>`。
- 进程退出 hook：`atexit` + SIGINT/SIGTERM 处理，退出前 final commit（防止 dirty 丢失）。
- `git init` 后若已有未提交内容，立即 initial commit（不等定时器）。

### 3.2 与 watcher 的关系
- committer 与 VaultWatcher 互不感知，各司其职。
- restore 时 `git reset/pull` 会批量改 `.md`，watcher 自然触发 reindex 尖峰；依赖 300ms 去抖 + ulid 幂等 upsert 兜底，不额外加 pause 端点。

### 3.3 集成点（src/everlingo/mem/vault/search/server.py）
- `AppState` 持有 `committer: Committer | None`。
- lifespan `state.open()` 时若 `load_git_backup().enabled` 则构造并 `committer.start()`；`state.close()` 时 `committer.stop()`（含 final commit）。
- 若 `enabled=false` 但 repo 已存在，committer 仅做 initial commit 兜底（不跑定时器、不 push）。

## 4. git 操作封装

新建 `src/everlingo/mem/vault/version/`：

```
version/
  __init__.py
  git.py          # subprocess 封装 git CLI：init/status/commit/push/pull/fetch/rebase/log/checkout
  committer.py     # Committer：定时器 + dirty 检测 + atexit final commit
  ssh_key.py       # 临时 ssh key 文件生命周期 + GIT_SSH_COMMAND 注入
  restore.py       # 恢复流程：commit → fetch → rebase → 冲突打 backup 分支
```

### 4.1 git.py
- 统一 `run_git(args, cwd=..., env=...)`，捕获 stdout/stderr。
- `is_repo(path)` / `init_repo(path)`（含 identity + initial commit + .gitignore）。
- `status_porcelain(path) -> bool`（有改动返回 True）。
- `commit(path, message)`。
- `push(path, remote, branch, force_lease=True)`（force-with-lease）。
- `fetch(path, remote)`。
- `rebase(path, upstream)` -> `(ok, conflict_files)`。
- `log(path, limit) -> list[{hash, time, message}]`。
- `checkout_to_backup_branch(path, commit_hash)`：把指定历史版本检出到 `backup/restore-<ts>` 分支（不直接覆盖工作区）。

### 4.2 ssh_key.py
- 持有 `auth.ssh_private_key_file`；非空 → 复制/软链到临时文件，`env["GIT_SSH_COMMAND"]="ssh -i <tmp> -o IdentitiesOnly=yes"`，操作后清理临时文件。
- 空 → 不注入 GIT_SSH_COMMAND（走系统 `~/.ssh/`）。

### 4.3 restore.py
```
restore_vault(memory_root, remote, branch) -> RestoreResult:
    1. commit(memory_root, "chore(vault): pre-restore snapshot")   # 捕获本地改动
    2. fetch(memory_root, remote)
    3. ok, conflicts = rebase(memory_root, f"{remote}/{branch}")
    4. if ok: return success
    5. else:
         backup_branch = f"backup/pre-restore-{ts}"
         create branch at current HEAD
         return conflict(backup_branch, conflicts)   # 由用户决定 hard reset
```
- hard reset 由调用方在用户确认后执行：`git reset --hard {remote}/{branch}`（backup 分支已兜底）。

## 5. indexer HTTP 端点（供 gateway UI / CLI 调用）

前缀建议：`/version`（indexer 进程内，FastAPI router）。

| Method | Path | 说明 |
|---|---|---|
| GET | `/version/status` | `{enabled, initialized, dirty, last_commit_at, last_push_at, remote_configured, ahead, behind}` |
| POST | `/version/commit` | 同步触发一次 commit |
| POST | `/version/push` | `--force-with-lease` push |
| POST | `/version/pull` | 走 restore 流程（commit→fetch→rebase），冲突返回 backup 分支 |
| GET | `/version/log?limit=20` | 最近 commit 列表 |
| POST | `/version/restore` `{commit_hash}` | 把指定历史版本检出到 backup 分支（不直接覆盖工作区） |

- 端点实现调用 `version/` 模块；与现有 `/{lang}/...` 路由平行，无 lang 维度。

## 6. CLI（docs/impl-spec/search/memory-vault-search-spec.md 的 mem 子命令扩展）

```
everlingo mem snapshot            # 同步触发一次 commit（即使 enabled=false 也尝试，repo 不存在则 init）
everlingo mem restore [--hard]    # 走 restore 流程；--hard 在冲突时 hard reset 到远端
everlingo mem push                # 手动 push --force-with-lease
everlingo mem pull                # 手动 pull（= restore 流程）
everlingo mem log [--limit N]     # 查看历史
```

- CLI 经 HTTP 委托 indexer 服务（同现有 `reindex` 范式），不直接碰 git。

## 7. 停掉 USER.md.bak

- `src/everlingo/tools/user_doc.py`：`user_doc_set` 移除写 `.bak` 逻辑（行 26–31）。
- `DOMAIN.md` 用户自由偏好笔记约束移除「写入前备份到 USER.md.bak」。
- `docs/impl-spec/chat-agent-tools-spec.md`：`user_doc_set` 描述移除 `.bak`。
- `tests/test_user_doc.py`：删两个 `.bak` 用例，改为断言"无 .bak 残留"。

## 8. reset_vault 安全网

- MCP `reset_vault` 工具（覆盖 `spec/` 模板）调用前，经 `version.git.commit()` 同步触发一次 commit，保存用户可能改过的 spec 进历史（避免 reset 丢失用户修改）。
- 实现：在 `vault_mcp_server.reset_vault` 路径内、`reset_vault` 实际覆盖文件前调 committer 的同步 commit（或 `git.commit(memory_root, ...)`）。

## 9. 测试

- `tests/test_version_git.py`：subprocess git CLI 封装（init / commit / push / pull / rebase / 冲突场景）。
- `tests/test_version_committer.py`：定时器 + debounce + dirty 检测 + atexit final commit。
- `tests/test_version_ssh_key.py`：临时 key 文件生命周期 + GIT_SSH_COMMAND 注入。
- `tests/test_version_restore.py`：restore 各分支（无冲突 / 可 rebase / 需 hard reset + backup 分支）。
- `tests/test_indexer_server_version.py`：`/version/*` 端点集成测试（mock workspace）。
- `tests/test_user_doc.py`：更新 `.bak` 用例为"无残留"断言。

## 10. 不在本期范围

- GitHub App / OAuth Connect 按钮（已决策弃用，见 ADR §5）。
- keychain 凭证存储（容器内不可用）。
- 协作式多机并发编辑冲突自动合并（定位为"单机使用 + 异机恢复"，冲突由用户手动处理）。
- UI console 页面（Phase 3）；PAT 凭证（Phase 4）。
