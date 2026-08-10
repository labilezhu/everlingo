# Tasks

## 计划的任务

（无）

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"

 - 2026-08-10 | Memory Vault 版本控制加固「启动强制统一本地分支名」：git.py 新增 rename_current_branch（git branch -M，幂等，失败仅告警不阻塞）+ init_repo 兼容 git<2.28（-b 失败降级 init + branch -M main）；Committer.start() init 后强制 rename 本地分支=配置 branch；测试补充 legacy-master repo 收敛到 main、rename 幂等/非 repo/降级路径；impl-spec vault-version-control.md §2.3/§4.1 补「强制统一分支名」说明。
 - 2026-08-10 | Memory Vault 版本控制与远端备份（实现 P1+2）：新增 src/everlingo/mem/vault/version/{git,committer,ssh_key,restore}.py（subprocess git CLI 封装，统一 safe.directory；定时器 commit 去抖 + push 间隔 + initial/final commit 兜底；临时私钥 + GIT_SSH_COMMAND；restore 冲突打 backup 分支）；models.py / setting.py 加 git_backup 配置段与 load/save_git_backup；search/server.py AppState 持 Committer 随 lifespan 启停、新增 /version/{status,commit,push,pull,log,restore} 端点；client.py / cli.py / main.py 加对应客户端方法与 mem snapshot/push/pull/restore/log/vstatus 子命令；tools/user_doc.py 停 USER.md.bak（改 git 回溯，DOMAIN.md/chat-agent-tools-spec.md 已在上一条更新）；mcp_server reset_vault 覆盖 spec 前 snapshot 安全网；测试 tests/test_version_{git,committer,ssh_key,restore}.py + tests/test_indexer_server_version.py + test_user_doc.py 更新；release notes 记 docs/release-notes/v0.1.2/。
 - 2026-08-10 | Memory Vault 版本控制与远端备份（设计定稿 + 文档）：覆盖 docs/ADR/20260810-vault-version-control.md（原 SaaS GitHub App + Contents API 方案标 superseded，新定本地 ws-container 方案：committer 在 indexer 进程、通用 git remote + git CLI、ssh/https_pat/https_none 三凭证、ws-master 不参与、everlingo.yaml 0600 兜底）；新写 docs/impl-spec/worksplace/vault-version-control.md（git repo 管理 / committer / git 操作封装 / indexer HTTP 端点 / CLI / 停 USER.md.bak / reset_vault 安全网 / 测试 / 分期 P1+2,P3,P4）；everlingo.example.yaml + user-docs/reference/configuration.md 加 git_backup 段；DOMAIN.md + chat-agent-tools-spec.md 移除 USER.md.bak 提及；deploy/deps-base/Dockerfile runtime stage 加 git openssh-client ca-certificates；deploy/ws-container/ws-container-spec.md 加「系统依赖」小节（git/openssh-client/ca-certificates 经 deps-base 共享）。TASKS + 后续实现排期见 vault-version-control.md §7。

