# Tasks

## 计划的任务

（无）

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"

 - 2026-08-04 | Me 页底部加版本信息；release 流程纳入源码版本号同步（MePage.tsx / ws_master / ws_router）
- 2026-08-04 | 【目标学习语言设置页】添加「重新初始化」按钮：MCP reset_vault 工具 + API 端点 + 前端按钮，重置 spec/ 目录（覆盖写入模板文件）
- 2026-08-04 | 笔记编辑器语言下拉默认选中 everlingo.yaml 的 target_language（GET /api/vault/langs 新增 default 字段，前端据此预选）
- 2026-08-04 | Web PWA 白屏修复：统一 fetch 401 兜底跳 /login（apiFetch.ts）+ React ErrorBoundary + 复活认证复检（useAuthRecheck）+ HTML 缓存头 no-store / assets immutable（web_acceptor.py、ws_router/app.py）；ADR 20260804-web-cache-control.md

