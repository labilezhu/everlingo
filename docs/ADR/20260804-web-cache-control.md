# ADR: Web PWA 白屏修复 — 认证失效兜底与缓存控制

- 状态：Accepted
- 日期：2026-08-04
- 决策参与方：用户、opencode
- 相关文档：
  - [多用户认证部署](../../user-docs/deployment/multiple-user-auth-deployment.md)
  - [简单单实例部署](../../user-docs/deployment/simple-single-deployment.md)

---

## 1. 动机

### 1.1 现象

按多用户认证部署（ws-router + ws-master + 动态 workspace 容器）运行的 EverLingo，作为 iPhone 主屏 PWA 使用一段时间后，会出现**打开应用白屏**。用户只能删除主屏图标重新添加才能恢复。

### 1.2 根因分析

排查确认项目**没有 Service Worker**（无 `sw.js`、无 workbox、无 `vite-plugin-pwa`），`manifest.webmanifest` 仅用于"加到主屏"，因此"PWA 网页缓存无法更新"的假设不成立。白屏的真正根因是三层叠加：

1. **认证失效后前端无兜底跳转**。JWT 由 `session_ttl` 控制过期，过期后 ws-router 中间件（`ws_router/middleware.py`）对 `Accept: text/html` 的请求返回 302 → `/login`（浏览器顶层导航有效），但对 fetch/XHR 返回 401 JSON。而前端**所有 fetch 均未统一处理 401**：
   - `web/src/main.tsx` 对 `/api/user-profile/status` 失败静默 `catch` 后继续渲染；
   - `sseClient.createSession()` 仅抛 `Error`，无重定向；
   - `target-language`、`pat` 等多处 `fetch().then(r => r.json())` 不检查 `r.ok`，401 时把 `{error:{...}}` 当业务数据访问字段 → `TypeError`。
2. **React 无 ErrorBoundary**。渲染期间异常会使整棵组件树卸载，直接白屏。
3. **iOS PWA 恢复不走顶层导航**。应用从后台/bfcache 复活时，服务端的 302 → `/login` 不会触发；页面直接以旧状态恢复并发出大量失效的 fetch。
4. **HTML 缓存无 Cache-Control**。`FileResponse` 未设缓存头，iOS 可能启发式缓存旧 HTML 外壳，叠加 bfcache 后需要"删图标重加"才能强制刷新。

## 2. 决策

| # | 决策点 | 选择 |
|---|---|---|
| 1 | 统一 fetch 包装 | 新增 `web/src/services/apiFetch.ts`：`apiFetch` / `apiFetchJson`，收到 401 且非登录页时 `window.location.replace('/login')` |
| 2 | ErrorBoundary | 新增 `web/src/components/ErrorBoundary.tsx`，所有页面根包裹；兜底显示"重新加载 / 重新登录"，替代白屏 |
| 3 | 复活时认证复检 | 新增 `web/src/services/useAuthRecheck.ts`，监听 `visibilitychange` 与 `pageshow(persisted)`，主动请求 `/api/user-profile/status` 复检 |
| 4 | SSE session_expired | 显示「会话已过期 [重新开始]」提示条，用户点按钮手动 `clearChatState` + 重建新 session，避免导航/卸载期间 EventSource 误触发 onerror 自动清空 sessionStorage 导致跨页跳转回来无法复用 session |
| 5 | HTML 缓存头 | HTML 外壳（`/login`、`/`、`/editor`、`/console/*`、`/self-service*`）加 `Cache-Control: no-store, must-revalidate`；`/assets/**`（内容 hash）加 `public, max-age=31536000, immutable`；`manifest.webmanifest` 加 `no-cache` |
| 6 | 简单部署兼容 | 401 兜底仅对真实 401 触发；简单单机部署无鉴权，恒 200，永不误跳 |

## 3. 变更内容

### 3.1 前端（`web/`）

| 文件 | 变更 |
|---|---|
| `src/services/apiFetch.ts` | **新增**。`ApiError`、`apiFetch()`（401 → 跳 /login）、`apiFetchJson()`（非 2xx 抛结构化 `ApiError`） |
| `src/services/useAuthRecheck.ts` | **新增**。`useAuthRecheck()` 钩子：`visibilitychange` + `pageshow(persisted)` 时复检认证态 |
| `src/components/ErrorBoundary.tsx` | **新增**。渲染异常兜底 UI（重新加载 / 重新登录） |
| `src/main.tsx` | 引导检查改走 `apiFetchJson`；`useAuthRecheck()` 复活复检；根包 `ErrorBoundary` |
| `src/{me,pat,self-service,web-console,target-language,editor,login}/main.tsx` | 根包 `ErrorBoundary` |
| `src/services/sseClient.ts` | `createSession` / `sendMessage` 改走 `apiFetchJson` |
| `src/components/ChatWindow.tsx` | `session_expired` 改为"重新加载"；移除已无用的 `reconnectNonce` / `handleRebuild` |
| `src/target-language/TargetLanguagePage.tsx` | 加载与保存改走 `apiFetchJson` / `apiFetch`；加 `useAuthRecheck()` |
| `src/pat/PatPage.tsx` | 改走 `apiFetch` |
| `src/editor/services/vaultApi.ts` | 改走 `apiFetch` |
| `src/web-console/useWechatChannelStatus.ts` | 改走 `apiFetch` |
| `src/login/LoginPage.tsx` | **不改**（POST /login 的 401 是"账号密码错误"，页内处理，不跳转） |

### 3.2 后端

`src/everlingo/gateway/web_acceptor.py`（简单部署与 workspace 容器前端入口）：

- 新增 `_static_response()` 帮助函数与 `HTML_CACHE_CONTROL` / `ASSET_CACHE_CONTROL` / `MANIFEST_CACHE_CONTROL` 常量
- HTML 路由（`/editor`、`/console/me`、`/console/me/target-language`、`/console/web-console`）与 catch-all 的 HTML 分支 → `no-store`
- `/assets/**` → immutable 长缓存；`/manifest.webmanifest` → `no-cache`

`src/everlingo/ws_router/app.py`（多用户部署前端入口）：

- 同样新增 `_static_response()` 与缓存常量
- `/login`、`/self-service`、`/self-service/pat` → `no-store`
- `/assets/**` → immutable 长缓存；`/manifest.webmanifest` → `no-cache`；图标 → immutable

## 4. 两种部署兼容性

前端是同一份 `web/dist` 产物，两种部署共用，因此决策必须对两者自洽：

| 行为 | 多用户部署 | 简单单机部署 |
|---|---|---|
| 401 跳 /login | JWT 过期时触发，正确 | 无鉴权，永不触发 |
| ErrorBoundary | 兜底白屏 | 兜底白屏 |
| `useAuthRecheck` | 401 时跳 /login | `/api/user-profile/status` 恒 200，无副作用 |
| SSE `session_expired` → reload | reload 后顶层导航 302 → /login | reload 后回到聊天页重新建会话 |
| 缓存头 | 同上 | 同上（`web_acceptor.py` 已覆盖） |

## 5. 不在本次范围

- **不引入 Service Worker**。当前修复（401 兜底 + ErrorBoundary + 复活复检 + 缓存头）已解决白屏；离线壳/可控更新留待后续，可选用 `vite-plugin-pwa`。
- 不改变认证机制（JWT 过期时长、cookie 属性等）。
- 不做"自动登出"计时器。
