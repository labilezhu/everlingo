# 决策：Memory Vault 版本控制与远端备份

- 日期：2026-08-10
- 状态：Accepted（**supersedes 同目录同名文档中 "SaaS GitHub App + Contents API" 方案**）
- 关联：docs/impl-spec/worksplace/vault-version-control.md

---

## 1. 背景

`$workspace/memory` 下的笔记库（USER.md + 各语言 vault 的 markdown 文件）是用户的学习记忆资产。需要：
- **版本管理**：追踪文件变更历史，可回溯到任意历史版本（例如误删一个 kb item 后能找回）。
- **远端备份**：把整库推到用户自己的 git remote（GitHub / GitLab / Gitea / 自建），实现异机恢复。

先前的讨论（本文档历史版本）基于一个 **SaaS 多用户云后端** 的前提，推荐 GitHub App + Installation Token + GitHub Contents API。但 EverLingo 的实际形态是 **单机本地应用 / 容器化的 ws-container**，且不希望 ws-master 介入用户 workspace 的内容管理。原 SaaS 方案在本形态下存在根本性的前提错位（详见 §5），故以本决策取代。

## 2. 决策

采用 **本地 git repo + 通用 git remote + `git` CLI** 的方案，全部 git 操作在 **ws-container 内部** 完成：

1. **`$workspace/memory` 是一个 git repo**（不是把整个 workspace 当 repo，避免把 `everlingo.yaml` / `logs/` / `plugins/` 卷入版本管理）。
2. **committer 归属 indexer 进程**：watcher 检测 `.md` 变更 → 去抖 `commit_interval` 秒 → 自动 `git commit`。indexer 是 single-writer 且已常驻监听文件变更，是 committer 的自然归宿。
3. **远端推送走 `git` CLI**（不是 GitHub Contents API）：`git push --force-with-lease`。保留对 fetch / pull / rebase / reset 的完整支持，满足"异机恢复"需求。
4. **通用 git remote，不绑死 GitHub**：`remote_url` 任意（git@github.com:user/vault.git / https://github.com/user/vault.git / 自建 git server 均可）。`https_pat` / `ssh` / `https_none` 三种凭证模式。
5. **凭证存储于 `everlingo.yaml` 的 `git_backup` 段（0600 文件保护）**，不依赖系统 keychain（容器内无 D-Bus / secret-service），也不经 ws-master。

## 3. 设计要点

### 3.1 git repo 与 gitignore
- `$workspace/memory/.git` 懒初始化（`git init` 时立即做 initial commit 捕获已有 vault）。
- repo-local 身份：`user.name=everlingo` / `user.email=noreply@everlingo.local`（不依赖用户 git 全局配置）。
- `.gitignore` 落盘内容：
  - 语言索引 DB：`languages/*/index/`（含 `memory.sqlite` / `-shm` / `-wal`，程序派生，可 `everlingo mem reindex --rebuild` 重建）
  - 程序临时文件：`**/vault/tmp/`
  - 历史遗留备份：`*.bak`（原 USER.md.bak 机制已停掉，见 §4）

### 3.2 committer 与 watcher 解耦
- committer **不订阅** watcher 事件，而是用定时器周期性跑 `git status --porcelain`，有 dirty 才 commit。避免事件风暴与细节耦合。
- 进程退出 hook（`atexit` + 信号）：退出前 final commit，避免 dirty 状态丢失。
- commit message：`chore(vault): auto-snapshot <ISO8601>`，无 conventional-commits 强约束。

### 3.3 恢复流程（异机恢复）
1. 先做同步 commit（捕获本地改动）。
2. `git fetch`。
3. 尝试 `git rebase`：无冲突直接完成。
4. 冲突时：先打 backup 分支 `backup/pre-restore-<ts>`，再由用户决定 `git reset --hard origin/<branch>`（hard reset 前已有 backup 分支兜底）。
5. restore 期间 indexer watcher 会自然触发 reindex 尖峰（依赖 300ms 去抖 + ulid 幂等 upsert 兜底），不额外加 pause 端点。

### 3.4 凭证管理
- **ssh**：`ssh_private_key_file` 为空 → 用系统 `~/.ssh/`（适用单机 / 已挂载 key 的容器）；非空 → 写临时文件 + `GIT_SSH_COMMAND` 注入，操作后清理。
- **https_pat**：用 `http.extraHeader=Authorization: Basic <base64(token:x-oauth-basic)>`。
- **https_none**：纯 https 无认证（私有 Gitea 等）。
- `pat` 在前端仅展示末 4 位掩码（写入时不带掩码）。

### 3.5 reset_vault 安全网
- MCP `reset_vault` 工具覆盖 `spec/` 模板前，同步触发一次 commit，把用户可能改过的 spec 先保存进历史（避免 reset 丢失用户修改）。

## 4. 与原设计的偏差

- **停掉 USER.md.bak 机制**：原 `tools/user_doc.py` 写入 USER.md 前生成 `.bak`。有了 git 历史后该机制冗余，移除（`DOMAIN.md` / `chat-agent-tools-spec.md` / `tests/test_user_doc.py` 同步更新）。

## 5. 为何不用原 SaaS GitHub App 方案

原文档（`docs/ADR/20260810-vault-version-control.md` 历史版本）推荐 GitHub App + Contents API，其论证依赖 SaaS 假设：
- "后端代用户 push，不能存 PAT" → 本地应用 PAT 只存本机，无服务器泄露风险。
- "GitHub App 的细粒度权限 / 短 token" → 本地应用无此收益。
- "Connect GitHub 三步 UX" → 本地应用走 OAuth callback 需 loopback / device flow，反而比 fine-grained PAT 更复杂。
- "用 Contents API 避免 clone/conflict" → 但本需求要**恢复（双向）**，Contents API 不支持 fetch/pull/rebase，实现恢复会更复杂。

故在本地 ws-container 形态下，原方案前提不成立，以本决策取代。

## 6. 多用户容器化部署兼容性

- 单机部署：用户直接编辑 `~/.everlingo/workspaces/default/everlingo.yaml` 的 `git_backup` 段。
- 多用户部署（ws-master 编排）：ws-master 用 template 初始化（默认 `enabled: false`），用户在 ws-container 内通过 console UI / CLI 编辑写入（复用 `save_profile` 模式）。
- **ws-master 不参与版本控制**：符合 "ws-container 可在简单使用情况下单独部署" 的设计原则（ws-master §10 关于 "LLM 密钥不写入 workspace" 的不变量在本特性上**不沿用** —— 明确接受 `git_backup` 凭证随 `everlingo.yaml` 落盘 workspace 的 trade-off，换取部署形态一致性）。
- 两种形态下 git 操作行为完全一致，凭证读取均来自 `everlingo.yaml`。

## 7. 分期

| Phase | 范围 |
|---|---|
| P1+2（首期） | ADR + spec + 本地版本管理（git.py + committer.py + git init 懒加载 + initial commit + atexit final commit + CLI snapshot）+ SSH 远端备份（ssh_key.py + push/pull + restore.py + indexer HTTP 端点）+ 停掉 USER.md.bak |
| P3（二期） | UI console 页 `/console/me/backup`（Me 页常驻入口）+ gateway REST API `/api/backup/*` + **配置热重载**（indexer `/version/apply-config` + `Committer.apply_config/reload_config`，保存配置即生效）+ **测试连接**（`/version/test`，ls-remote 探测）+ **Hard Reset 强操作**（`/version/reset-hard`） |
| P4（三期） | HTTPS + PAT 凭证支持 + PAT 掩码 |

## 8. 替代方案评估

- **GitHub App + Contents API（原方案）**：前提为 SaaS，本地形态下 UX 与安全收益均劣化，弃用。
- **每语言独立 git repo**：repo 更小但 USER.md 需另管、多 repo 配置翻倍，弃用。
- **dulwich（pure-python git）**：避免 `git` CLI 依赖但 merge 支持弱，shelling out 更务实。
- **keychain 存凭证**：容器内无 D-Bus / secret-service 不可用，弃用，改用 `everlingo.yaml` 0600。
