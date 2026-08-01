# Tasks

## 计划的任务

（无）

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"

- 2026-08-01 | WS-Router 登录页改为 React SPA（Vite + React + Tailwind + shadcn/ui，复用 `web/` 项目新增 `login` 入口），移除 Python 硬编码登录 HTML；WS-Router 本地服务 `/login`、`/assets/*`、`/favicon.png`、`/manifest.webmanifest`、`/icon-*.png`（pre-auth 白名单）；`POST /login` 改为 JSON-only；`deploy/ws-router/Dockerfile` 增加 frontend-builder stage 携带 `web/dist`。见 [ws-router.md](./docs/impl-spec/multiple-users/ws-router.md) §4.3 / [deploy.md](./docs/impl-spec/multiple-users/deploy.md) §5.2
- 2026-08-01 | 在 `web/src/me/MePage.tsx` 底部新增「退出登录」按钮（`GET /logout`，仅多用户 WS-Router 拓扑有效），并更新 [ws-console-arch.md](./docs/impl-spec/workspace-console/ws-console-arch.md) §6.6 记录跨拓扑行为
- 2026-08-01 | WS-Router 新增认证自服务页：`/self-service`（退出登录 + 「永久 Token」入口）与 `/self-service/pat`（PAT 列表 + 生成，仅输入 label），独立 Vite entry（`self-service.html` / `pat.html`），POST-auth 访问；新增 WS-Master `GET /internal/users/{user_id}/pat`（list，不含 token_hash）与 `MasterClient.pat_list` / `pat_create` 封装，create 复用既有 `POST /internal/pat`。见 [ws-router.md](./docs/impl-spec/multiple-users/ws-router.md) §4.6 / [internal-api-contract.md](./docs/impl-spec/multiple-users/internal-api-contract.md) §2.4
- 2026-08-01 | Workspace Console Me 页底部「退出登录」按钮改为「账号」入口（跳 WS-Router `/self-service`，`UserRound` 图标），退出登录集中到 WS-Router 自服务页；更新 [ws-console-arch.md](./docs/impl-spec/workspace-console/ws-console-arch.md) §6.6 跨拓扑行为（单用户拓扑下点击回落到 chatbot SPA）

