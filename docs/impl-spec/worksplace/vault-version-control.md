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
- **启动时强制统一本地分支名**：committer `start()` 对已存在 repo（如用户手动 `git init` / 异机 clone 恢复，本地可能在 `master` 等其它分支名）执行 `git branch -M <branch>`，保证本地当前分支名恒等于配置分支，从而 `push origin <branch>` / `rebase origin/<branch>` / status 的 ahead-behind（`HEAD...origin/<branch>`）全链路自洽；memory repo 是单分支工作区，`-M` 只改名、不丢 commit。

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

### 3.4 配置热重载（P3）
- `Committer.apply_config(backup: GitBackup)`：用传入配置替换内存副本，重配 SSH 上下文；按新 `enabled` 幂等启停定时线程（`enabled=true` 且未在跑时先 `_ensure_repo()` 兜底 init + initial commit，再启动线程）。
- `Committer.reload_config() -> GitBackup`：重新从 `setting.load_git_backup()` 读取并 `apply_config`，返回新配置。
- 由 indexer 端点 `POST /version/apply-config` 触发（gateway 保存 `everlingo.yaml` 后调用），实现**保存配置即生效、无需重启 indexer**。`stop()` 的 final commit 行为不受热重载影响。

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
- `is_repo(path)` / `init_repo(path)`（含 identity + initial commit + .gitignore；`git init -b main`，git<2.28 降级 `init` + `branch -M main`）。
- `status_porcelain(path) -> bool`（有改动返回 True）。
- `rename_current_branch(path, target)`：`git branch -M target`，幂等，强制统一本地分支名。
- `commit(path, message)`。
- `push(path, remote, branch, force_lease=True)`（force-with-lease）。
- `fetch(path, remote)`。
- `rebase(path, upstream)` -> `(ok, conflict_files)`。
- `log(path, limit) -> list[{hash, time, message}]`。
- `checkout_to_backup_branch(path, commit_hash)`：把指定历史版本检出到 `backup/restore-<ts>` 分支（不直接覆盖工作区）。
- `test_remote(path, remote_url, *, env, config) -> (ok, message)`：`git ls-remote --heads <url>` 只读连通探测（P3，供「测试连接」按钮），不修改本地 repo 状态。

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
| POST | `/version/apply-config` | **P3**：gateway 保存 `everlingo.yaml` 后触发 committer 热重载（`reload_config()`），保存配置即生效 |
| POST | `/version/test` | **P3**：用 `git_backup` 凭证跑 `ls-remote`，返回 `{ok, message}` 连通探测结果（「测试连接」） |
| POST | `/version/reset-hard` | **P3**：强操作 `commit → fetch → git reset --hard origin/<branch>`（丢弃本地差异；UI 需二次确认） |

- 端点实现调用 `version/` 模块；与现有 `/{lang}/...` 路由平行，无 lang 维度。

## 5.1 gateway REST API（P3，`/api/backup/*`）

gateway 进程新增 `src/everlingo/gateway/backup_api.py`（router `prefix=/api/backup`），是 UI 的唯一后端入口：

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/backup/status` | 聚合 repo 状态（透传 `/version/status`） |
| GET | `/api/backup/config` | 当前 `git_backup` 配置；`auth.pat` 以掩码返回（末 4 位，ADR §3.4），避免泄露 |
| POST | `/api/backup/config` | 校验后写 `everlingo.yaml`（`save_git_backup`），随后调 `/version/apply-config` 热重载；接受 `method ∈ {ssh, https_pat, https_none}`；`pat` 以 `pat_changed` 布尔声明是否改动（omit 或 false → 保留原值；true → 用提交值，空串=清空） |
| POST | `/api/backup/snapshot` | 透传 `/version/commit` |
| POST | `/api/backup/push` | 透传 `/version/push` |
| POST | `/api/backup/pull` | 透传 `/version/pull`（软恢复） |
| POST | `/api/backup/test` | 透传 `/version/test` |
| POST | `/api/backup/reset-hard` | 透传 `/version/reset-hard`（强操作） |
| GET | `/api/backup/log?limit=20` | 透传 `/version/log` |
| POST | `/api/backup/restore` `{commit_hash}` | 透传 `/version/restore` |

- 调用链路：gateway 经 `SearchClient`（httpx + unix socket `indexer.sock`）委托 indexer 的 `/version/*`；`SearchClient` 是同步阻塞，FastAPI 端点内用 `run_in_threadpool` 包裹。
- 配置读写直接走 `setting.load_git_backup()` / `save_git_backup()`（gateway 与 indexer 同容器、共享 `everlingo.yaml`）。
- indexer 不可达 / 返回异常 → 端点返回 503（前端展示「无法连接服务」）。
- P4：凭证 UI 支持 `ssh` / `https_pat` / `https_none`；`https_pat` 时展示 PAT 输入框（值以掩码回填），保存按 `pat_changed` 语义处理（见上表）。

## 5.2 UI console 页（P3，`/console/me/backup`）

- 前端新增独立多入口页 `web/backup.html` + `web/src/backup/BackupPage.tsx`（Vite `rollupOptions.input` 加 `backup`），gateway `web_acceptor.py` 新增 `GET /console/me/backup` 服务该 HTML。
- 页面组成：
  - **状态卡**：enabled / initialized / dirty / 上次 commit / ahead-behind / remote_url / branch（`GET /api/backup/status`）。
  - **配置表单**：enabled 开关、remote_url、branch、method（ssh | https_pat | https_none）、ssh_private_key_file（仅 ssh 显示）、pat（仅 https_pat 显示，掩码回填）；保存走 `POST /api/backup/config`。
  - **操作区**：测试连接、立即快照、立即推送、拉取恢复、**Hard Reset 到远端**（`window.confirm` 二次确认）。
  - **历史列表**：来自 `GET /api/backup/log`。
- Me 页（`web/src/me/MePage.tsx`）**常驻入口**「远端备份」→ `/console/me/backup`（不按 enabled/initialized 条件显隐）。
- i18n：新增 `backup` 命名空间（`web/src/locales/{zh-CN,en}/backup.json`），注册进 `i18n.ts` 的 `NS` / `RESOURCES`。

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
- `tests/test_indexer_server_version.py`：`/version/*` 端点集成测试（mock workspace），含 `apply-config` 热重载、`test` 无 remote 降级。
- `tests/test_backup_api.py`（P3/P4）：gateway `/api/backup/*` 路由测试（mock SearchClient + 真实 yaml 落盘），覆盖状态、配置读写（ssh/https_pat/https_none）、pat 掩码与 `pat_changed` 语义（omit 保留 / 改值 / 清空）、各操作端点、indexer 不可达降级 503。
- `tests/test_version_committer.py`（P3）：`apply_config` 启停定时线程、`reload_config` 从 yaml 重读生效。
- `tests/test_user_doc.py`：更新 `.bak` 用例为"无残留"断言。

## 10. 不在本期范围

- GitHub App / OAuth Connect 按钮（已决策弃用，见 ADR §5）。
- keychain 凭证存储（容器内不可用）。
- 协作式多机并发编辑冲突自动合并（定位为"单机使用 + 异机恢复"，冲突由用户手动处理）。

## 11. 分期现状

| Phase | 范围 | 状态 |
|---|---|---|
| P1+2 | ADR + spec + 本地版本管理（git.py + committer.py + git init 懒加载 + initial commit + atexit final commit + CLI snapshot）+ SSH 远端备份（ssh_key.py + push/pull + restore.py + indexer HTTP 端点）+ 停掉 USER.md.bak | 已实现 |
| P3 | UI console 页 `/console/me/backup` + gateway REST API `/api/backup/*` + Me 页常驻入口 + 配置热重载（§3.4）+ 测试连接（`/version/test`）+ Hard Reset 强操作（`/version/reset-hard`） | 已实现 |
| P4 | HTTPS + PAT 凭证支持 + PAT 掩码 | 已实现 |

## 12. 部署依赖与容器运行时

### 12.1 镜像系统依赖
- ws-container 镜像需 `git` + `openssh-client` + `ca-certificates`，由 `deploy/deps-base/Dockerfile` runtime stage 统一安装（ws-master / ws-router 镜像共享此 base，无害）。详见 [ws-container-spec.md](/deploy/ws-container/ws-container-spec.md)「系统依赖」。
- 启动探测 `git --version`：缺失时 `enabled` 强制 false + log warning，不阻塞主流程。

### 12.2 safe.directory（挂载 workspace 的 UID 不匹配）
- 多用户部署下 `<host_workspace_dir>` 由宿主用户（如 root / deploy 用户）拥有，容器内进程是 `everlingo` UID 1000。git 见到文件 owner UID ≠ 当前 euid 会报 `detected dubious ownership` 并拒绝操作。
- 缓解：`version/git.py` 的 `run_git` 每次调用带 `-c safe.directory=<abs memory_root>`（或 env `GIT_CONFIG_GLOBAL=/dev/null` + `-c safe.directory=*`），避免依赖全局 config（容器内 `/home/everlingo/.gitconfig` 在容器重建后丢失）。

### 12.3 ssh host key 验证
- `git@github.com` 等 ssh 远端首次连接会要求确认 host key，非交互 subprocess 下默认 `host key verification failed`。
- `version/ssh_key.py` 构造的 `GIT_SSH_COMMAND` 必须含 `-o StrictHostKeyChecking=accept-new`（首次自动接受并写入 known_hosts，后续严格校验）。

### 12.4 https 模式的 TLS
- `git push https://github.com/...` 需要 CA 证书做 TLS 验证；`ca-certificates` 已在 base 安装。自建 git server 用自签证书时需用户自行 `http.sslVerify=false`（配置项或 `-c`）。

### 12.5 HOME 与全局 config
- git / ssh 可能读 `$HOME`（/home/everlingo）。容器内 everlingo 用户 HOME 已就绪；为避免跨容器重建丢失全局 config，所有 git 配置均走 repo-local（init 时设 `user.name` / `user.email`）或命令行 `-c` / env，不写全局 `~/.gitconfig`。
