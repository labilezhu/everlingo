# Tasks

## 计划的任务

（无）

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"

 - 2026-08-10 | Memory Vault 版本控制与远端备份（设计定稿 + 文档）：覆盖 docs/ADR/20260810-vault-version-control.md（原 SaaS GitHub App + Contents API 方案标 superseded，新定本地 ws-container 方案：committer 在 indexer 进程、通用 git remote + git CLI、ssh/https_pat/https_none 三凭证、ws-master 不参与、everlingo.yaml 0600 兜底）；新写 docs/impl-spec/worksplace/vault-version-control.md（git repo 管理 / committer / git 操作封装 / indexer HTTP 端点 / CLI / 停 USER.md.bak / reset_vault 安全网 / 测试 / 分期 P1+2,P3,P4）；everlingo.example.yaml + user-docs/reference/configuration.md 加 git_backup 段；DOMAIN.md + chat-agent-tools-spec.md 移除 USER.md.bak 提及；deploy/deps-base/Dockerfile runtime stage 加 git openssh-client ca-certificates；deploy/ws-container/ws-container-spec.md 加「系统依赖」小节（git/openssh-client/ca-certificates 经 deps-base 共享）。TASKS + 后续实现排期见 vault-version-control.md §7。

