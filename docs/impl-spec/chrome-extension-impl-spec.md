# Chrome Extension 实现详细设计

- 关联文档：[chrome-extension-spec.md](../docs/impl-spec/chrome-extension-spec.md)（产品 / 架构 / session 生命周期 / envelope 构造规则）
- 适用范围：本文档是 [chrome-extension-spec.md](../docs/impl-spec/chrome-extension-spec.md) 的**实现级补充**，聚焦代码结构、文件清单、依赖与构建流程。当本文档与 spec 冲突时以 spec 为准。

---

## 1. 决策汇总

| # | 决策 | 理由 |
|---|---|---|---|
| 1 | 手动 Vite multi-entry，不使用 `@crxjs/vite-plugin` | 只需 1 background + 1 sidecar + 1 options HTML，加一个依赖换 HMR 价值不高 |
| 2 | deps 列表与 `web/` 相同 + `@types/chrome` + `vitest` | 复用现有技术栈，不引入新框架 |
| 3 | API base URL 通过 options 页面配置到 `chrome.storage.local`，运行时通过 `getApiBaseUrl()` 异步读取 | 支持用户自定义服务端地址 |
| 4 | 扩展图标点击 / 右键菜单选中文本 → 发 `TRIGGER_TRANSLATE` 消息给 sidecar → sidecar 重新抓取选词并发起翻译 | 支持 sidecar 已打开时重复触发 |
| 5 | 右键菜单固定 task=translate（菜单文本"用小记🐹翻译"），与 sidecar 内 task 切换无关 | 用户确认"始终 translate" |
| 6 | 7 步全部实现，产出可 load unpacked 的 CRX | 一步到位 |
| 7 | vitest 对纯函数（envelope 构造 + context 提取 + URL 规范化）写单测 | 核心逻辑回归保护，UI 不测 |

---

## 2. 目录结构

```
extension/
├── manifest.json               # MV3: activeTab + sidePanel + storage + scripting
├── package.json                # 独立 deps
├── vite.config.ts              # multi-entry: sidecar.html + background.ts
├── tsconfig.json               # 与 web/ 一致 + chrome types
├── components.json             # shadcn 配置（从 web/ 拷贝）
├── vitest.config.ts            # vitest 配置
├── README.md                   # 开发 / 构建 / 加载流程
├── public/
│   └── icons/
│       ├── icon16.png          # 由 docs/arts/chrome-icon.png 缩放
│       ├── icon48.png
│       └── icon128.png
└── src/
    ├── background.ts           # service worker
    ├── sidecar.html            # sidecar HTML 入口
    ├── sidecar.tsx             # React 入口
    ├── options.html            # options 页面 HTML 入口
    ├── options.tsx             # options 页面 React 入口
    ├── index.css               # Tailwind + 主题（从 web/ 拷贝）
    ├── config.ts               # server_url 读写 + URL 规范化
    ├── types/
    │   ├── chat.ts             # 从 web/ 拷贝
    │   └── envelope.ts         # envelope TS 类型（对应 Python schema）
    ├── lib/
    │   └── utils.ts            # 从 web/ 拷贝 (cn)
    ├── services/
    │   ├── sseClient.ts        # 改造: 全 URL + envelope body
    │   ├── backgroundClient.ts # chrome.runtime.sendMessage 封装
    │   └── messageHistory.ts   # chrome.storage.session msgs 读写
    ├── content/
    │   ├── extract.ts          # selection + context.text 提取算法
    │   └── extract.test.ts     # vitest
    └── components/
        ├── ChatWindow.tsx       # 改造: session 查询 + history 恢复 + envelope 构造
        ├── ChatInput.tsx        # 从 web/ 拷贝
        ├── MessageBubble.tsx    # 从 web/ 拷贝
        ├── MarkdownRenderer.tsx # 从 web/ 拷贝
        ├── TaskSelector.tsx     # 新增: task 切换按钮
        └── ui/
            ├── button.tsx       # 从 web/ 拷贝
            ├── input.tsx        # 从 web/ 拷贝
            └── textarea.tsx     # 从 web/ 拷贝
```

**组件复用策略**（与 spec §3 一致）：

- 从 `web/src/components/` 拷贝 `ChatInput` / `MessageBubble` / `MarkdownRenderer` / `ui/*` 到 `extension/src/components/`，**独立维护**
- `ChatWindow.tsx` 是改造版（session 查询 + UI history 恢复 + envelope 构造逻辑不同）
- 拷贝的组件首次拷贝时一字不改，后续两个仓的组件演进方向会逐渐分歧

---

## 3. 依赖清单（package.json）

```json
{
  "name": "everlingo-extension",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite build --watch",
    "build": "tsc && vite build",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "@base-ui/react": "^1.6.0",
    "@fontsource-variable/geist": "^5.2.9",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "lucide-react": "^1.21.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-markdown": "^9.0.0",
    "remark-gfm": "^4.0.0",
    "tailwind-merge": "^3.6.0",
    "tw-animate-css": "^1.4.0"
  },
  "devDependencies": {
    "@tailwindcss/vite": "^4.3.1",
    "@types/chrome": "^0.0.260",
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "shadcn": "^4.11.0",
    "tailwindcss": "^4.3.1",
    "typescript": "^5.4.0",
    "vite": "^5.4.0",
    "vitest": "^2.0.0"
  }
}
```

依赖项与 `web/package.json` 对齐（参见 `web/package.json`），新增：
- `@types/chrome` — Chrome Extension API 类型
- `vitest` — 纯函数单测

**不引入** `@crxjs/vite-plugin`：手动 Vite multi-entry 已足够。

---

## 4. manifest.json

```json
{
  "manifest_version": 3,
  "name": "记了么 - EverLingo",
  "version": "0.1.0",
  "description": "有记忆的 AI 外语老师 - 浏览器选词翻译与笔记",
  "permissions": ["activeTab", "sidePanel", "storage", "scripting", "contextMenus"],
  "options_ui": {
    "page": "options.html",
    "open_in_tab": true
  },
  "action": {
    "default_title": "打开小记🐹",
    "default_icon": {
      "16": "icons/icon16.png",
      "48": "icons/icon48.png",
      "128": "icons/icon128.png"
    }
  },
  "side_panel": {
    "default_path": "sidecar.html"
  },
  "background": {
    "service_worker": "background.js",
    "type": "module"
  },
  "icons": {
    "16": "icons/icon16.png",
    "48": "icons/icon48.png",
    "128": "icons/icon128.png"
  }
}
```

权限说明见 [chrome-extension-spec.md §4](../docs/impl-spec/chrome-extension-spec.md)。`scripting` 权限用于 `chrome.scripting.executeScript` 在页面上下文执行 selection/context 提取脚本（详见 §8）。

---

## 5. 构建配置

### vite.config.ts

```ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'path';

export default defineConfig({
  plugins: [tailwindcss(), react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: {
        sidecar: 'src/sidecar.html',
        background: 'src/background.ts',
      },
      output: {
        entryFileNames: '[name].js',
        chunkFileNames: 'chunks/[name]-[hash].js',
        assetFileNames: 'assets/[name].[ext]',
      },
    },
  },
});
```

**注意**：
- 无 `server.proxy`（扩展不走 Vite dev server，直接调后端绝对 URL）
- `build --watch` 模式用于开发：构建到 `dist/`，Chrome 重新加载扩展即可
- 输出文件名固定 `[name].js`，避免 manifest 中 `background.js` 路径变化

### tsconfig.json

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "types": ["chrome"],
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["src"]
}
```

与 `web/tsconfig.json` 一致，新增 `"types": ["chrome"]`。

### vitest.config.ts

```ts
import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
});
```

---

## 6. Background service worker

文件：`extension/src/background.ts`

### 职责

1. **onInstalled**：生成 `device_id` (uuid v4) 存 `chrome.storage.local`；创建右键菜单；调用 `chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true })` 设全局 panel（点图标 toggle，切 tab 保持显示）
2. **contextMenus.onClicked**：用户右键菜单"用小记🐹翻译"时触发 `triggerTranslate(tabId)`（图标点击由 `setPanelBehavior` 接管，不再触发 `onClicked`）
3. **runtime.onMessage**：处理 `GET_SESSION` 消息（spec §5.2 步骤 3-6）

### 消息协议

**入消息**：
```ts
{ type: 'GET_SESSION' }
```

**出消息（响应）**：
```ts
{ sessionId: string; fresh: boolean }
```

### 实现伪代码

```ts
// 安装时生成 device_id + 创建右键菜单 + 设全局 panel
chrome.runtime.onInstalled.addListener(async () => {
  await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });

  const { device_id } = await chrome.storage.local.get('device_id');
  if (!device_id) {
    await chrome.storage.local.set({ device_id: crypto.randomUUID() });
  }

  chrome.contextMenus.create({
    id: 'translate-selection',
    title: '用小记🐹翻译',
    contexts: ['selection'],
  });
});

// 右键菜单点击 → 触发翻译（图标点击由 setPanelBehavior 接手，不再触发 onClicked）
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === 'translate-selection' && tab?.id != null) {
    triggerTranslate(tab.id);
  }
});

// 处理 GET_SESSION 消息
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type !== 'GET_SESSION') return false;
  handleGetSession().then(sendResponse).catch(() => sendResponse({ error: true }));
  return true;  // async response
});

async function handleGetSession(): Promise<{ sessionId: string; fresh: boolean }> {
  const tab = (await chrome.tabs.query({ active: true }))[0];
  const tabId = tab.id!;
  const sidKey = `sid:${tabId}`;
  const { [sidKey]: existingSid } = await chrome.storage.session.get(sidKey);

  if (existingSid) {
    // 探活
    const ok = await probeSession(existingSid);
    if (ok) return { sessionId: existingSid, fresh: false };
  }

  // 新建 session：先清理 UI history，再 POST
  await chrome.storage.session.remove(`msgs:${tabId}`);
  const newSid = await createSession();
  await chrome.storage.session.set({ [sidKey]: newSid });
  return { sessionId: newSid, fresh: true };
}

async function probeSession(sid: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/session/${sid}/events`, {
      method: 'GET',
      headers: { Accept: 'text/event-stream' },
    });
    return res.ok;  // 200 = session 存在
    // 注意：这里发起的 SSE 连接需立即关闭，仅作探活用
  } catch {
    return false;
  }
}

async function createSession(): Promise<string> {
  const res = await fetch(`${API_BASE_URL}/api/session`, { method: 'POST' });
  const data = await res.json();
  return data.session_id;
}
```

**探活细节**：`probeSession` 用 `fetch` 发 GET 请求拿到响应头即关闭连接，不真正建立长期 SSE。SSE 长连接由 sidecar panel 自己建立（§9）。

---

## 7. 类型与配置

### `extension/src/config.ts`

```ts
export const DEFAULT_API_BASE_URL = 'http://localhost:8000';
export const SERVER_URL_STORAGE_KEY = 'server_url';
export const SERVER_USERNAME_STORAGE_KEY = 'server_username';
export const SERVER_PASSWORD_STORAGE_KEY = 'server_password';

// 规范化：去除首尾空格，校验 scheme，去除尾斜杠
export function normalizeUrl(input: string): string {
  let url = input.trim();
  if (!url) return DEFAULT_API_BASE_URL;
  if (!/^https?:\/\//i.test(url)) {
    throw new Error('URL 必须以 http:// 或 https:// 开头');
  }
  url = url.replace(/\/+$/, '');
  return url;
}

// 从 chrome.storage.local 读取用户配置的 server_url，未设置时返回默认值
export async function getApiBaseUrl(): Promise<string> {
  const { [SERVER_URL_STORAGE_KEY]: stored } = await chrome.storage.local.get(SERVER_URL_STORAGE_KEY);
  if (typeof stored === 'string' && stored) {
    try {
      return normalizeUrl(stored);
    } catch {
      return DEFAULT_API_BASE_URL;
    }
  }
  return DEFAULT_API_BASE_URL;
}

// 从 chrome.storage.local 读取 Basic Auth 凭据，未设置时返回空字符串
export async function getApiAuth(): Promise<{ username: string; password: string }> {
  const items = await chrome.storage.local.get([SERVER_USERNAME_STORAGE_KEY, SERVER_PASSWORD_STORAGE_KEY]);
  return {
    username: typeof items[SERVER_USERNAME_STORAGE_KEY] === 'string' ? items[SERVER_USERNAME_STORAGE_KEY] : '',
    password: typeof items[SERVER_PASSWORD_STORAGE_KEY] === 'string' ? items[SERVER_PASSWORD_STORAGE_KEY] : '',
  };
}

// 构造 HTTP Basic Auth 的 Authorization 请求头值；username 为空时返回 null（不启用）
export function buildBasicAuthHeader(username: string, password: string): string | null {
  const u = username.trim();
  if (!u) return null;
  return 'Basic ' + btoa(unescape(encodeURIComponent(`${u}:${password}`)));
}

// 聚合获取 baseUrl + authHeader，供 background/sidecar 初始化时调用
export async function getApiConfig(): Promise<{ baseUrl: string; authHeader: string | null }> {
  const [baseUrl, { username, password }] = await Promise.all([
    getApiBaseUrl(),
    getApiAuth(),
  ]);
  return {
    baseUrl,
    authHeader: buildBasicAuthHeader(username, password),
  };
}
```

调用方（background、sidecar）各自在初始化时 `await getApiConfig()` 获取 base URL 与 Basic Auth header，传递给 services 层的 `sendEnvelope(baseUrl, sessionId, env, authHeader)` / `connectSSE(baseUrl, sessionId, onEvent, onError, authHeader)`。修改配置后需重新打开 sidecar 生效。

### `extension/src/types/envelope.ts`

TS 类型对应 Python `UserInputEnvelope`（见 [envelope-spec.md §2](../docs/impl-spec/envelope-spec.md)）：

```ts
export type TaskKind = 'translate' | 'look_up' | 'none';
export type SurfaceKind = 'sidecar' | 'popup' | 'fullscreen';
export type SourceKind = 'plain' | 'web' | 'chrome_ext' | 'pdf' | 'epub' | 'ios_app';

export interface ChatPart { message: string; }
export interface SelectionPart { text: string; }
export interface ScreenshotPart { data_url: string; mime: string; }
export interface ContextPart {
  text: string;
  kind: 'paragraph' | 'page' | 'screen' | 'plain';
  screenshot?: ScreenshotPart;
}

export interface SourcePlain { kind: 'plain'; }
export interface SourceWeb {
  kind: 'web';
  url: string;
  title: string;
  surface: 'fullscreen';
}
export interface SourceChromeExt {
  kind: 'chrome_ext';
  url: string;
  title: string;
  surface: 'sidecar' | 'popup';
}
// SourcePdf / SourceEpub / SourceIosApp 预留，MVP 不用

export type SourcePart = SourcePlain | SourceWeb | SourceChromeExt;

export interface DevicePart {
  platform: 'chrome_ext' | 'ios_app' | 'pdf_reader' | 'web' | 'cli';
  device_id?: string;
  locale?: string;
  timezone?: string;
}

export interface UserInputEnvelope {
  schema_version: 1;
  task: TaskKind;
  chat: ChatPart;
  selection: SelectionPart;
  context: ContextPart;
  source: SourcePart;
  device?: DevicePart;
}
```

### `extension/src/types/chat.ts`

从 `web/src/types/chat.ts` 拷贝（Message / SSEEvent / uid）。

---

## 8. Content 提取算法

文件：`extension/src/content/extract.ts`

实现 [chrome-extension-spec.md §6.3](../docs/impl-spec/chrome-extension-spec.md) 的 `context.text` 提取算法。

```ts
const BLOCK_TAGS = new Set([
  'P', 'DIV', 'SECTION', 'ARTICLE', 'LI',
  'H1', 'H2', 'H3', 'H4', 'H5', 'H6',
  'BLOCKQUOTE', 'PRE', 'TD',
]);

function isBlockElement(el: Element | null): el is Element {
  if (!el || !el.tagName) return false;
  return BLOCK_TAGS.has(el.tagName.toUpperCase());
}

export function extractContextText(selection: Selection): string {
  if (!selection.rangeCount) return '';
  const range = selection.getRangeAt(0);
  let block: Element | null = range.commonAncestorContainer as Element;
  while (block && !isBlockElement(block)) {
    block = block.parentElement;
  }
  if (block) {
    const text = block.textContent || '';
    return text.length > 500 ? text.slice(0, 500) : text;
  }
  // 回退：选区前后各 250 字
  const fullText = document.body.innerText;
  const start = Math.max(0, range.startOffset - 250);
  return fullText.slice(start, start + 500);
}

export function extractSelection(): string {
  return window.getSelection()?.toString() || '';
}

export function extractPageInfo(): { url: string; title: string } {
  return { url: location.href, title: document.title };
}
```

**执行方式**：这些函数在页面上下文执行，通过 `chrome.scripting.executeScript` 调用：

```ts
const [result] = await chrome.scripting.executeScript({
  target: { tabId },
  func: () => {
    // 这里 inline 调用 extract.ts 中的函数
    const selection = window.getSelection()?.toString() || '';
    // ... context.text 提取
    return { selection, context, url: location.href, title: document.title };
  },
});
```

注意 `chrome.scripting.executeScript` 的 `func` 参数在页面上下文执行，**不能直接 import** `extract.ts`。实现时要么把算法 inline 到 `func` 中，要么用 `files` 参数注入打包后的脚本。MVP 倾向 inline，保持单文件可见。

---

## 9. Services 层

### `extension/src/services/backgroundClient.ts`

```ts
interface GetSessionResponse {
  sessionId: string;
  fresh: boolean;
  error?: boolean;
}

export async function getSession(): Promise<GetSessionResponse> {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ type: 'GET_SESSION' }, resolve);
  });
}
```

### `extension/src/services/sseClient.ts`

改造自 `web/src/services/sseClient.ts`。与原版的差异：
- URL 用绝对地址 `${baseUrl}/api/...`
- 新增可选 `authHeader` 参数注入 HTTP Basic Auth
- 移除 `createSession`（由 background 通过 `backgroundClient.getSession()` 处理）
- **SSE 改用 `@microsoft/fetch-event-source`**：原生 `EventSource` 无法自定义请求头，`fetchEventSource` 基于 `fetch`，可注入 `Authorization` 头，同时支持 `AbortSignal` 清理连接。

**SSE 自动重连**（`connectSSE`）：

| 场景 | `ConnStatus` | 行为 |
|------|-------------|------|
| 连接成功 | `{ state: 'connected' }` | 重置退避计数 |
| 网络中断 / 瞬时错误 | `{ state: 'reconnecting', attempt, countdown }` | 指数退避 1s→2s→4s→...→30s 封顶，`onerror` 内 `throw` 接管库的重试调度 |
| 404 session 过期 | `{ state: 'session_expired' }` | `onerror` 内 `throw` 停止重连，不再自动重试 |

`onerror` 的关键语义：
- **返回数字 N** → 库 `setTimeout(create, N)`，即 N 毫秒后重试。**返回 0 是立即重试**，不是"停止重连"。
- **抛出异常 (throw)** → 库调用 `dispose()` + `reject()`，不再自动重试。

```ts
import { fetchEventSource } from '@microsoft/fetch-event-source';
import type { UserInputEnvelope } from '@/types/envelope';
import type { SSEEvent } from '@/types/chat';

export type ConnStatus =
  | { state: 'connected' }
  | { state: 'reconnecting'; attempt: number; countdown: number }
  | { state: 'session_expired' };

export interface ConnectSSEResult {
  cleanup: () => void;
  retryNow: () => void;
}

export async function sendEnvelope(
  baseUrl: string,
  sessionId: string,
  env: UserInputEnvelope,
  authHeader?: string | null,
): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (authHeader) {
    headers['Authorization'] = authHeader;
  }
  const res = await fetch(`${baseUrl}/api/session/${sessionId}/message`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ envelope: env }),
  });
  if (!res.ok) throw new Error('Failed to send envelope');
}

class SessionExpiredError extends Error {
  constructor() {
    super('Session expired');
    this.name = 'SessionExpiredError';
  }
}

const MAX_BACKOFF_MS = 30_000;

export function connectSSE(
  baseUrl: string,
  sessionId: string,
  onEvent: (e: SSEEvent) => void,
  onStatus: (s: ConnStatus) => void,
  authHeader?: string | null,
): ConnectSSEResult {
  let abortController = new AbortController();
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let countdownTimer: ReturnType<typeof setInterval> | null = null;
  let attempt = 0;
  let closed = false;

  const headers: Record<string, string> = {};
  if (authHeader) {
    headers['Authorization'] = authHeader;
  }

  function backoffMs(): number {
    return Math.min(1000 * Math.pow(2, attempt), MAX_BACKOFF_MS);
  }

  function clearCountdown() {
    if (countdownTimer !== null) {
      clearInterval(countdownTimer);
      countdownTimer = null;
    }
  }

  function startConnection() {
    abortController = new AbortController();
    fetchEventSource(`${baseUrl}/api/session/${sessionId}/events`, {
      signal: abortController.signal,
      headers,
      openWhenHidden: true,
      async onopen(response) {
        if (response.status === 404) {
          throw new SessionExpiredError();
        }
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const contentType = response.headers.get('content-type');
        if (!contentType?.startsWith('text/event-stream')) {
          throw new Error(`Expected content-type text/event-stream, Actual: ${contentType}`);
        }
        attempt = 0;
        clearCountdown();
        onStatus({ state: 'connected' });
      },
      onmessage(msg) {
        try {
          const parsed = JSON.parse(msg.data);
          if (msg.event === 'typing_hint') {
            onEvent({ type: 'typing_hint', data: parsed });
          } else if (msg.event === 'sound') {
            onEvent({ type: 'sound', data: parsed });
          } else {
            onEvent({ type: 'message', data: parsed });
          }
        } catch { /* skip */ }
      },
      onerror(err) {
        if (err instanceof SessionExpiredError) {
          closed = true;
          clearCountdown();
          onStatus({ state: 'session_expired' });
          throw err;
        }
        if (closed) return;
        scheduleRetry();
        throw new Error('take over retry');
      },
    }).catch(() => {});
  }

  function scheduleRetry() {
    if (closed) return;
    attempt++;
    const delay = backoffMs();
    let remaining = Math.ceil(delay / 1000);
    onStatus({ state: 'reconnecting', attempt, countdown: remaining });
    countdownTimer = setInterval(() => {
      remaining--;
      if (remaining >= 0) {
        onStatus({ state: 'reconnecting', attempt, countdown: remaining });
      }
    }, 1000);
    retryTimer = setTimeout(() => {
      clearCountdown();
      startConnection();
    }, delay);
  }

  function cleanup() {
    closed = true;
    abortController.abort();
    if (retryTimer !== null) {
      clearTimeout(retryTimer);
      retryTimer = null;
    }
    clearCountdown();
  }

  function retryNow() {
    if (retryTimer !== null) {
      clearTimeout(retryTimer);
      retryTimer = null;
    }
    clearCountdown();
    abortController.abort();
    if (!closed) {
      attempt = 0;
      startConnection();
    }
  }

  startConnection();

  return { cleanup, retryNow };
}
```

> **CORS 说明**：扩展（origin = `chrome-extension://<id>`）请求后端 API 属于跨源。服务端 `web_acceptor.py` 已启用 CORSMiddleware（`allow_origins=["*"]`，详见 [web-session-acceptor.md](../docs/impl-spec/web-session-acceptor.md) §）。无需在 manifest 中申请 `host_permissions`。

### `extension/src/services/messageHistory.ts`

实现 spec §7.4 的 UI message history 持久化。

```ts
import type { Message } from '@/types/chat';

const HISTORY_LIMIT_BYTES = 10 * 1024 * 1024;  // 10MB chrome.storage.session 单项限制

export interface UIMessageRecord {
  role: 'user' | 'assistant';
  text: string;
  timestamp: string;
}

export async function loadHistory(tabId: number): Promise<UIMessageRecord[]> {
  const key = `msgs:${tabId}`;
  const { [key]: msgs } = await chrome.storage.session.get(key);
  return (msgs as UIMessageRecord[]) || [];
}

export async function appendMessage(
  tabId: number,
  record: UIMessageRecord,
): Promise<void> {
  const key = `msgs:${tabId}`;
  const existing = await loadHistory(tabId);

  // 去重：用 timestamp 作 key（SSE 重连可能重复推送）
  if (record.role === 'assistant' && existing.some(
    m => m.role === 'assistant' && m.timestamp === record.timestamp
  )) {
    return;
  }

  const next = [...existing, record];
  // FIFO 淘汰：超出 10MB 丢头部
  let bytes = JSON.stringify(next).length;
  while (bytes > HISTORY_LIMIT_BYTES && next.length > 1) {
    next.shift();
    bytes = JSON.stringify(next).length;
  }
  await chrome.storage.session.set({ [key]: next });
}

export async function clearHistory(tabId: number): Promise<void> {
  await chrome.storage.session.remove(`msgs:${tabId}`);
}
```

---

## 10. Sidecar panel React 应用

### `extension/src/sidecar.html`

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>小记🐹 - EverLingo</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="./sidecar.tsx"></script>
  </body>
</html>
```

### `extension/src/sidecar.tsx`

```tsx
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import ChatWindow from './components/ChatWindow';
import './index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ChatWindow />
  </StrictMode>,
);
```

### `extension/src/components/ChatWindow.tsx`（改造版）

启动流程对应 spec §5.2 步骤 2a-10：

```tsx
import { useCallback, useEffect, useRef, useState } from 'react';
import MessageBubble from './MessageBubble';
import ChatInput from './ChatInput';
import TaskSelector from './TaskSelector';
import { connectSSE, sendEnvelope } from '@/services/sseClient';
import { getSession } from '@/services/backgroundClient';
import { loadHistory, appendMessage, UIMessageRecord } from '@/services/messageHistory';
import type { UserInputEnvelope, TaskKind } from '@/types/envelope';
import { Message, uid } from '@/types/chat';

const TAB_ID = ...;  // 通过 chrome.tabs.getCurrent() 获取

export default function ChatWindow() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [task, setTask] = useState<TaskKind>('translate');
  const [messages, setMessages] = useState<Message[]>([]);
  const [thinking, setThinking] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // ... audio / endRef 与 web/ ChatWindow 一致

  // 缓存本次 sidecar 打开周期内的 selection/context 快照
  const snapshotRef = useRef<{ selection: string; context: string; url: string; title: string }>({
    selection: '', context: '', url: '', title: '',
  });

  useEffect(() => {
    let cleanup: (() => void) | undefined;
    (async () => {
      try {
        // 步骤 2a: 恢复 UI history
        const history = await loadHistory(TAB_ID);
        if (history.length > 0) {
          setMessages(history.map(h => ({
            id: uid(),
            text: h.text,
            from: h.role === 'user' ? 'user' : 'bot',
          })));
        }

        // 步骤 2b: 查 session
        const { sessionId: sid, fresh } = await getSession();

        // 步骤 7: 若 fresh=true 清空 UI
        if (fresh) {
          setMessages([]);
        }

        setSessionId(sid);

        // 步骤 8: 提取 selection/context（通过 chrome.scripting.executeScript）
        const snapshot = await extractSnapshot();
        snapshotRef.current = snapshot;

        // 步骤 8: 连 SSE
        cleanup = connectSSE(sid, handleSSEEvent, () => setError('连接断开'));

        // 步骤 9: 若 selection 非空，自动发首次 envelope
        if (snapshot.selection) {
          await sendFirstEnvelope(sid, task, snapshot);
        }
      } catch (err) {
        setError('初始化失败');
      }
    })();
    return () => { cleanup?.(); };
  }, []);

  function handleSSEEvent(e: SSEEvent) {
    if (e.type === 'message') {
      const text = (e.data as { text: string; timestamp: string }).text;
      const ts = (e.data as { timestamp: string }).timestamp;
      setMessages(prev => [...prev, { id: uid(), text, from: 'bot' }]);
      appendMessage(TAB_ID, { role: 'assistant', text, timestamp: ts });
      setPending(false);
      setThinking(false);
    } else if (e.type === 'sound') {
      // 与 web/ ChatWindow 一致
    } else {
      setThinking((e.data as { typing: boolean }).typing);
    }
  }

  const handleSend = useCallback(async (text: string) => {
    if (!sessionId) return;
    setMessages(prev => [...prev, { id: uid(), text, from: 'user' }]);
    setPending(true);
    appendMessage(TAB_ID, { role: 'user', text, timestamp: new Date().toISOString() });
    try {
      const env = buildEnvelope(task, text, snapshotRef.current);
      await sendEnvelope(sessionId, env);
    } catch {
      setPending(false);
      setError('发送消息失败');
    }
  }, [sessionId, task]);

  // ... JSX 与 web/ ChatWindow 类似，布局调整为固定窄宽度
  return (
    <div className="flex flex-col h-screen border-x border-border">
      <header>...</header>
      <TaskSelector task={task} onChange={setTask} />
      {error && <div>...</div>}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">...</div>
      <ChatInput onSend={handleSend} disabled={!sessionId} pending={pending} />
    </div>
  );
}

function buildEnvelope(
  task: TaskKind,
  chatMessage: string,
  snap: { selection: string; context: string; url: string; title: string },
): UserInputEnvelope {
  return {
    schema_version: 1,
    task,
    chat: { message: chatMessage },
    selection: { text: snap.selection },
    context: { text: snap.context, kind: snap.context ? 'paragraph' : 'plain' },
    source: {
      kind: 'chrome_ext',
      url: snap.url,
      title: snap.title,
      surface: 'sidecar',
    },
    device: {
      platform: 'chrome_ext',
      device_id: '...',  // 从 chrome.storage.local 读
      locale: navigator.language,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    },
  };
}
```

### `extension/src/components/TaskSelector.tsx`（新增）

```tsx
import { Button } from '@/components/ui/button';
import type { TaskKind } from '@/types/envelope';
import { cn } from '@/lib/utils';

const TASKS: { value: TaskKind; label: string }[] = [
  { value: 'translate', label: '翻译' },
  { value: 'look_up', label: '查词' },
  { value: 'none', label: '聊天' },
];

export default function TaskSelector({
  task, onChange,
}: { task: TaskKind; onChange: (t: TaskKind) => void }) {
  return (
    <div className="flex gap-1 px-3 py-2 border-b border-border">
      {TASKS.map(t => (
        <Button
          key={t.value}
          size="sm"
          variant={task === t.value ? 'default' : 'outline'}
          onClick={() => onChange(t.value)}
        >
          {t.label}
        </Button>
      ))}
    </div>
  );
}
```

### 拷贝不修改的组件

从 `web/src/components/` 拷贝到 `extension/src/components/`：
- `ChatInput.tsx`
- `MessageBubble.tsx`
- `MarkdownRenderer.tsx`
- `ui/button.tsx`
- `ui/input.tsx`
- `ui/textarea.tsx`

从 `web/src/lib/` 拷贝：
- `utils.ts`

从 `web/src/` 拷贝：
- `index.css`
- `types/chat.ts`

> **字号设定**：sidecar 面板宽度在 360–480px 之间，`index.css` 中设置 `html { font-size: 17px }` 以提升可读性，所有 Tailwind `text-*` rem 类按此基准等比放大。

### 消息内链接点击行为

消息内容中的 markdown 链接由 `react-markdown` 渲染为 `<a>`，默认 `target="_blank" rel="noopener noreferrer"`（新 Tab 打开）。

与 [Standalone Web Chatbot](./web-chatbot.md) 不同的是，Chrome Extension sidecar 不引入 `LinkListenerContext` 机制：
- sidecar 没有"被宿主应用嵌入"的场景
- 所有链接统一在新 Tab 打开，无拦截需求
- 这是两仓组件演进方向逐渐分歧的预期结果（参见 §2）

---

## 11. 测试

### `extension/src/content/extract.test.ts`

vitest 单测 `extractContextText` 算法。由于算法依赖 DOM，用 jsdom 或手动 mock `Selection` / `Element`。

**测试用例**：
1. selection 在 `<p>` 内 → 返回该 `<p>` 的 textContent（截断 500 字）
2. selection 在嵌套 `<div><p>` 内 → 找到最近 block 祖先
3. selection 无 block 祖先 → 回退前后 250 字
4. block textContent 超 500 字 → 截断
5. selection 为空 → 返回空字符串

### `extension/src/types/envelope.test.ts`

**测试用例**：
1. `buildEnvelope` 默认 task=translate 时各字段正确
2. `buildEnvelope` selection/context 为空时字段仍存在（不 undefined）
3. `buildEnvelope` source.kind='chrome_ext' + source.surface='sidecar'

### 运行测试

```bash
cd extension && npm test
```

---

## 12. 开发与构建流程

### 开发

```bash
# 1. 启动后端
cd /home/labile/everlingo
uv run gateway --channel_web

# 2. 构建 extension（watch 模式）
cd extension
npm install
npm run dev  # vite build --watch

# 3. 加载扩展
# Chrome → chrome://extensions → 开启"开发者模式" → "加载已解压的扩展程序"
# 选择 extension/dist 目录
```

### 构建

```bash
pushd extension
npm run build  # tsc 类型检查 + vite build
# 产物在 extension/dist/
popd
```

### 验证流程

1. 启动 gateway
2. 加载 unpacked extension
3. 打开任意网页，选中一个词
4. 点击扩展图标 → sidecar 打开
5. 检查 sidecar 内是否显示翻译结果
6. 关闭 sidecar，20 分钟内重开 → 检查 UI history 恢复
7. 关闭 sidecar，等 21 分钟后重开 → 检查新建 session + UI 清空

---

## 13. 实施步骤

按以下顺序执行，每步完成后可独立验证：

### Step 1: Scaffold
- 新建目录与配置文件（§3-5）
- `npm install`
- 验证：`npm run build` 能产出 `dist/`（即便 src 为空也能跑通构建链路）

### Step 2: Background service worker
- 写 `extension/src/background.ts`（§6）
- 验证：load unpacked 后点击扩展图标能打开 sidecar（sidecar 暂为空 HTML）

### Step 3: 类型 + 纯函数 + 测试
- 写 `types/envelope.ts`、`content/extract.ts`、`config.ts`、`types/chat.ts`、`lib/utils.ts`（§7-8）
- 写 `extract.test.ts`、`envelope.test.ts`（§11）
- 验证：`npm test` 全绿

### Step 4: Services 层
- 写 `services/backgroundClient.ts`、`services/sseClient.ts`、`services/messageHistory.ts`（§9）
- 验证：TypeScript 编译通过

### Step 5: Sidecar panel
- 写 `sidecar.html`、`sidecar.tsx`、`components/ChatWindow.tsx`、`components/TaskSelector.tsx`（§10）
- 拷贝 `ChatInput` / `MessageBubble` / `MarkdownRenderer` / `ui/*` / `index.css`
- 验证：load unpacked 后 sidecar 能渲染聊天界面，选词能触发翻译

### Step 6: 图标
- 使用 `docs/arts/chrome-icon.png` 缩放生成 3 个 PNG（16/48/128，保留 alpha）
- 在 `manifest.json` 的 `action` 块中显式添加 `default_icon`，指向 icons 目录

### Step 7: README
- 写 `extension/README.md`（§12 开发与构建流程）

---

## 14. Options 页面与右键菜单

### 14.1 Options 页面

- **入口**：`extension/options.html` → `extension/src/options.tsx` → `extension/src/components/OptionsForm.tsx`
- **技术栈**：React + Tailwind，与 sidecar 一致
- **功能**：服务端地址 + 服务端用户名 + 服务端密码（`type="password"`，含眼睛切换显示图标）三字段 + 保存 + 测试连接
- **校验**：
  - 地址：`normalizeUrl()` — 去首尾空格、必须 `http://` 或 `https://` 开头、去尾斜杠
  - 用户名/密码：无格式校验，留空则不启用 HTTP Basic Auth
- **测试连接**：用当前表单值构造请求，`GET /api/session/__probe__/events` + 3s 超时 abort：
  | 响应 | 提示 |
  |---|---|
  | 200 / 404 | ✅ 连接成功 |
  | 401 / 403 | ❌ 用户名或密码错误 |
  | 网络超时/错误 | ❌ 无法连接 / 连接超时 |
- **存储**：`chrome.storage.local` 的 `server_url` / `server_username` / `server_password` 三个键，默认值分别为 `http://localhost:8000` / `''` / `''`
- **manifest**：`"options_ui": { "page": "options.html", "open_in_tab": true }`

### 14.2 扩展图标与右键菜单

**图标点击**（`setPanelBehavior({ openPanelOnActionClick: true })`）：
- Chrome 自动 toggle 全局 panel，不触发 `action.onClicked` 事件
- panel 首次打开时 sidecar init 流程自动 capture snapshot + 发 envelope（若 selection 非空）
- panel 已打开时重复点击仅隐藏/显示面板，不触发翻译

**右键菜单"用小记🐹翻译"**：
1. 用户选中文本后右键菜单
2. Background `triggerTranslate(tabId)`：
   - `chrome.sidePanel.open({ tabId })`（打开全局 panel，确保可见。全局 panel 模式下 `open({ tabId })` 仅用于定位窗口，不影响全局性）
   - `chrome.runtime.sendMessage({ type: 'TRIGGER_TRANSLATE', task: 'translate' })`
3. Sidecar `chrome.runtime.onMessage` 监听 `TRIGGER_TRANSLATE`：
   - `sessionId` 未就绪 → 忽略（init 流程会处理首次抓取+发送）
   - `sessionId` 已就绪 → 重新 `captureSnapshot()` → 若 `selection` 非空 → 用 `task='translate'` 构造 envelope → `sendEnvelope` → append UI history

**竞态处理**：sidecar 刚打开时 `runtime.sendMessage` 可能因 listener 尚未注册而被静默丢包 → init 流程的 capture+send 作为兜底。

### 14.3 右键菜单

- **权限**：`"contextMenus"`（manifest permissions）
- **创建**：`onInstalled` 时 `chrome.contextMenus.create({ id: 'translate-selection', title: '用小记🐹翻译', contexts: ['selection'] })`
- **响应**：`chrome.contextMenus.onClicked` → 触发 `triggerTranslate(tabId)`，与图标点击共享同一路径
