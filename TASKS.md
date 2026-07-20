# Current Sprint

## 进行中的任务

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"

- 2026-07-20 | **侧边栏 fontSize 调大**: `extension/src/index.css` 设置 `html { font-size: 17px }`，等比放大所有 `text-*` rem 类，提升 sidecar 可读性；同步更新 `chrome-extension-impl-spec.md` §10 注释
- 2026-07-20 | **设计 + 实现**: Chrome Extension 选词翻译 sidecar
  - **设计文档**：[chrome-extension-spec.md](/docs/impl-spec/chrome-extension-spec.md)（架构/session 生命周期/envelope 构造/UI history）+
    [chrome-extension-impl-spec.md](/extension/chrome-extension-impl-spec.md)（实现详细设计）
  - **Schema 扩展**：`SourceWeb.surface` 字段（sidecar/popup/fullscreen，默认 fullscreen）+ `ContextPart.screenshot` 可选 + `ScreenshotPart` model
  - **Agent system prompt**：`task=look_up` 空输入延续语义规则；source 字段说明更新（已落地 plain 与 web）
  - **WebChannel 超时**：`DISCONNECT_GRACE` 300s → 1200s
  - **Chrome Extension 代码**（`extension/` 子目录）：
    - Scaffold：package.json / tsconfig / vite multi-entry / manifest.json MV3 / index.css / placeholder icons
    - Background service worker：device_id 生成、GET_SESSION 消息处理、session 探活/创建/重用
    - 类型 + 纯函数：envelope TS 类型（含 buildEnvelope）、extract.ts（selection + context.text 算法 + captureSnapshot）
    - Services：sseClient（全 URL + envelope body）/ backgroundClient / messageHistory（chrome.storage.session UI history 持久化）
    - Sidecar panel React 组件：ChatWindow（session 查询 + UI history 恢复 + envelope 自动发送 + SSE 处理 + TaskSelector task 切换按钮）
    - 组件拷贝：ChatInput / MessageBubble / MarkdownRenderer / ui/* / lib/utils / types/chat（从 web/ 拷贝）
    - 测试：12 个 vitest 用例（extract.test.ts + envelope.test.ts）
   - **所有后端改动测试**：+18 个测试用例，全量回归通过
    - **Bugfix: CORS 缺失导致 sidecar "连接断开"**（[issue 描述]：扩展跨源请求无 CORS 响应头，浏览器拦截响应体 → `sessionId` 变为 `undefined` → 所有后续请求路径含 `undefined` → sidecar 提示断开）
      - 服务端 `web_acceptor.py`：挂载 FastAPI CORSMiddleware（`allow_origins=["*"]`）
      - 扩展端 `backgroundClient.ts`：`getSession()` 校验 `error`/`sessionId` 后 reject，防止 `undefined` 静默传染
      - 扩展端 `background.ts`：`probeSession()` 拿到响应头后立即 `controller.abort()` 关闭 SSE 流
      - 测试：`test_web_acceptor.py` 新增 `TestCORS`（OPTIONS 预检、POST session、SSE 三种场景）
      - 文档：更新 `web-session-acceptor.md`（CORS 配置小节）+ `chrome-extension-impl-spec.md`（Services 节 CORS 说明）
- 2026-07-20 | **Chrome Extension 增强：Options 配置 + sidecar 已打开时选词重翻 + 右键菜单**
  - **Options 页面**：React + Tailwind 实现 server_url 配置表单（`chrome.storage.local` 持久化），默认 `http://localhost:8000`，URL 规范化（去尾斜杠、scheme 校验）；`config.ts` 改为 `getApiBaseUrl()` 异步函数
  - **已打开 sidecar 重翻**：background `action.onClicked` 发 `TRIGGER_TRANSLATE` 消息 → sidecar `runtime.onMessage` 监听 → 重新 `captureSnapshot` + `sendEnvelope`（task=translate）
  - **右键菜单**：manifest 加 `"contextMenus"` 权限；`onInstalled` 创建菜单项；`onClicked` 与图标点击共享 `triggerTranslate(tabId)` 路径
  - **sseClient**：`sendEnvelope` / `connectSSE` 改为接收 `baseUrl` 参数（由调用方通过 `getApiBaseUrl()` 获取）
- **测试**：+5 个 `normalizeUrl` vitest 用例
- **文档**：更新 `chrome-extension-spec.md`（§4 权限 + §10 未来优化）+ `chrome-extension-impl-spec.md`（§1 决策 / §2 目录 / §4 manifest / §7 config / §9 Services / 新增 §14 Options 与右键菜单）+ `extension/README.md`
- 2026-07-20 | **图标替换：占位图标 → `docs/arts/chrome-icon.png` 缩放版**
  - 从 `docs/arts/chrome-icon.png`（1254×1254 RGBA）缩放生成 16/48/128 PNG（保留 alpha）
  - `manifest.json` `action` 块增加 `default_icon` 显式声明工具栏图标
  - 更新 `chrome-extension-impl-spec.md` §2 目录注释 + §4 manifest 示例 + §13 Step 6 措辞
  - 重构建 `dist/` 生效
