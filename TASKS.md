# Tasks

## 计划的任务

（无）

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"

- 2026-08-01 | WS-Router 登录页改为 React SPA（Vite + React + Tailwind + shadcn/ui，复用 `web/` 项目新增 `login` 入口），移除 Python 硬编码登录 HTML；WS-Router 本地服务 `/login`、`/assets/*`、`/favicon.png`、`/manifest.webmanifest`、`/icon-*.png`（pre-auth 白名单）；`POST /login` 改为 JSON-only；`deploy/ws-router/Dockerfile` 增加 frontend-builder stage 携带 `web/dist`。见 [ws-router.md](./docs/impl-spec/multiple-users/ws-router.md) §4.3 / [deploy.md](./docs/impl-spec/multiple-users/deploy.md) §5.2
- 2026-08-01 | 在 `web/src/me/MePage.tsx` 底部新增「退出登录」按钮（`GET /logout`，仅多用户 WS-Router 拓扑有效），并更新 [ws-console-arch.md](./docs/impl-spec/workspace-console/ws-console-arch.md) §6.6 记录跨拓扑行为

