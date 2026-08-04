# Tasks

## 计划的任务

（无）

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"

 - 2026-08-04 | Me 页底部加版本信息；release 流程纳入源码版本号同步（MePage.tsx / ws_master / ws_router）
- 2026-08-04 | 【目标学习语言设置页】添加「重新初始化」按钮：MCP reset_vault 工具 + API 端点 + 前端按钮，重置 spec/ 目录（覆盖写入模板文件）
- 2026-08-04 | 笔记编辑器语言下拉默认选中 everlingo.yaml 的 target_language（GET /api/vault/langs 新增 default 字段，前端据此预选）
- 2026-08-04 | Web PWA 白屏修复：统一 fetch 401 兜底跳 /login（apiFetch.ts）+ React ErrorBoundary + 复活认证复检（useAuthRecheck）+ HTML 缓存头 no-store / assets immutable（web_acceptor.py、ws_router/app.py）；ADR 20260804-web-cache-control.md
 - 2026-08-04 | 修复 gateway 重启后 SSE session_expired 死循环：session_expired 时自动清空 sessionStorage 持久化会话并重建新 session，不再依赖「重新加载」按钮
 - 2026-08-04 | 修复跨页跳转（chatbot ↔ Me 等按钮）后回来每次都新建 chat session：session_expired 自动清空 sessionStorage 的设计在页面卸载/导航期间 EventSource 误触发 onerror 时会把存储同步清掉，导致跨页回来无法复用 sid。回退为 spec 规定的「手动重启」UI（显示「会话已过期 [重新开始]」提示条，用户点击才 clearChatState + 重建），同步更新 ADR 20260804 第 4 项

