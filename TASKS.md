# Tasks

## 计划的任务

（无）

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"

- 2026-08-01 | WS-Router 登录页改为 React SPA（Vite + React + Tailwind + shadcn/ui，复用 `web/` 项目新增 `login` 入口），移除 Python 硬编码登录 HTML；WS-Router 本地服务 `/login`、`/assets/*`、`/favicon.png`、`/manifest.webmanifest`、`/icon-*.png`（pre-auth 白名单）；`POST /login` 改为 JSON-only；`deploy/ws-router/Dockerfile` 增加 frontend-builder stage 携带 `web/dist`。见 [ws-router.md](./docs/impl-spec/multiple-users/ws-router.md) §4.3 / [deploy.md](./docs/impl-spec/multiple-users/deploy.md) §5.2
- 2026-08-01 | 在 `web/src/me/MePage.tsx` 底部新增「退出登录」按钮（`GET /logout`，仅多用户 WS-Router 拓扑有效），并更新 [ws-console-arch.md](./docs/impl-spec/workspace-console/ws-console-arch.md) §6.6 记录跨拓扑行为
- 2026-08-01 | WS-Router 新增认证自服务页：`/self-service`（退出登录 + 「永久 Token」入口）与 `/self-service/pat`（PAT 列表 + 生成，仅输入 label），独立 Vite entry（`self-service.html` / `pat.html`），POST-auth 访问；新增 WS-Master `GET /internal/users/{user_id}/pat`（list，不含 token_hash）与 `MasterClient.pat_list` / `pat_create` 封装，create 复用既有 `POST /internal/pat`。见 [ws-router.md](./docs/impl-spec/multiple-users/ws-router.md) §4.6 / [internal-api-contract.md](./docs/impl-spec/multiple-users/internal-api-contract.md) §2.4
- 2026-08-01 | Workspace Console Me 页底部「退出登录」按钮改为「账号」入口（跳 WS-Router `/self-service`，`UserRound` 图标），退出登录集中到 WS-Router 自服务页；更新 [ws-console-arch.md](./docs/impl-spec/workspace-console/ws-console-arch.md) §6.6 跨拓扑行为（单用户拓扑下点击回落到 chatbot SPA）
- 2026-08-01 | 解除 `target_language` 与 `interface_language` 互斥约束（允许相同）：`models.py` 删 `UserProfile.validate()` 互斥分支、`target_language` description 去约束；`DOMAIN.md` 删三处约束；`everlingo.example.yaml` 注释去约束；`tests/test_setting.py` 删负向用例并新增 `test_same_languages_allowed`；`agent.py` `dest_lang` 回退规则补 LLM 自主兜底。见 [ADR 20260801](./docs/ADR/20260801-user-onboarding.md) §2
- 2026-08-01 | 用户首次使用引导与目标学习语言设置页（ADR §10 步骤 2~6）：后端新建 `src/everlingo/gateway/user_profile_api.py`（`GET /api/user-profile/status`、`GET /api/target-language/list`、`POST /api/target-language/default`，复用 MCP client `list_vaults`/`create_vault`，indexer 不可达降级为 `null`/503），挂载到 `web_acceptor.py`；新增 `tests/test_user_profile_api.py`（12 用例，含 create_vault 静默调用与 yaml 写回）；前端新增 `web/target-language.html` + `web/src/target-language/` 设置页（引导模式 + 单选列表 + 静默保存）、`web_acceptor.py` 增加 `/console/me/target-language` fallback、Me 页增加「目标学习语言」入口；chatbot 首页 `web/src/main.tsx` 改 async bootstrap（render 前 fetch status，`needs_setup` 跳转设置页）。更新 [ws-console-arch.md](./docs/impl-spec/workspace-console/ws-console-arch.md) §5.2/§5.3/§6.1/§6.2、[ws-console.md](./docs/impl-spec/workspace-console/ws-console.md) 导航图、[DOMAIN.md](./DOMAIN.md) 补录术语。见 [ADR 20260801](./docs/ADR/20260801-user-onboarding.md) §10
- 2026-08-01 | 新增 [target-lang-setting.md](./docs/impl-spec/workspace-console/target-lang-setting.md) 专文，集中记录「目标学习语言设置页」的前后端设计与逻辑（API 契约、页面元素、引导模式、首页强制跳转、副作用联动），并在 [ws-console-arch.md](./docs/impl-spec/workspace-console/ws-console-arch.md) §5.2 与 [ws-console.md](./docs/impl-spec/workspace-console/ws-console.md)（导航 + 文档索引）处引用

