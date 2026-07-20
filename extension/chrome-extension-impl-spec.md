# Chrome Extension 实现详细设计

- 状态：Planned（2026-07）
- 关联文档：[chrome-extension-spec.md](../docs/impl-spec/chrome-extension-spec.md)（产品 / 架构 / session 生命周期 / envelope 构造规则）
- 适用范围：本文档是 [chrome-extension-spec.md](../docs/impl-spec/chrome-extension-spec.md) 的**实现级补充**，聚焦代码结构、文件清单、依赖与构建流程。当本文档与 spec 冲突时以 spec 为准。

---

## 1. 决策汇总

| # | 决策 | 理由 |
|---|---|---|
| 1 | 手动 Vite multi-entry，不使用 `@crxjs/vite-plugin` | 只需 1 background + 1 sidecar HTML，加一个依赖换 HMR 价值不高 |
| 2 | deps 列表与 `web/` 相同 + `@types/chrome` + `vitest` | 复用现有技术栈，不引入新框架 |
| 3 | API base URL 硬编码在 `extension/src/config.ts` | MVP 简单直接，生产前修改 |
| 4 | 7 步全部实现，产出可 load unpacked 的 CRX | 一步到位 |
| 5 | vitest 对纯函数（envelope 构造 + context 提取）写单测 | 核心逻辑回归保护，UI 不测 |

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
│       ├── icon16.png          # 占位图标
│       ├── icon48.png
│       └── icon128.png
└── src/
    ├── background.ts           # service worker
    ├── sidecar.html            # sidecar HTML 入口
    ├── sidecar.tsx             # React 入口
    ├── index.css               # Tailwind + 主题（从 web/ 拷贝）
    ├── config.ts               # API_BASE_URL 等常量
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
  "permissions": ["activeTab", "sidePanel", "storage", "scripting"],
  "action": {
    "default_title": "打开小记🐹"
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

1. **onInstalled**：生成 `device_id` (uuid v4) 存 `chrome.storage.local`
2. **action.onClicked**：`chrome.sidePanel.open({ tabId })` 打开 sidecar
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
// 安装时生成 device_id
chrome.runtime.onInstalled.addListener(async () => {
  const { device_id } = await chrome.storage.local.get('device_id');
  if (!device_id) {
    await chrome.storage.local.set({ device_id: crypto.randomUUID() });
  }
});

// 点击扩展图标 → 打开 sidecar
chrome.action.onClicked.addListener((tab) => {
  if (tab.id != null) {
    chrome.sidePanel.open({ tabId: tab.id });
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
// 后端 API 基础 URL
// 开发时指向本地 gateway；生产部署前修改为线上地址
export const API_BASE_URL = 'http://localhost:8000';
```

### `extension/src/types/envelope.ts`

TS 类型对应 Python `UserInputEnvelope`（见 [envelope-spec.md §2](../docs/impl-spec/envelope-spec.md)）：

```ts
export type TaskKind = 'translate' | 'look_up' | 'none';
export type SurfaceKind = 'sidecar' | 'popup' | 'fullscreen';
export type SourceKind = 'plain' | 'web' | 'pdf' | 'epub' | 'ios_app';

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
  surface: SurfaceKind;
}
// SourcePdf / SourceEpub / SourceIosApp 预留，MVP 不用

export type SourcePart = SourcePlain | SourceWeb;

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

改造自 `web/src/services/sseClient.ts`：

```ts
import { API_BASE_URL } from '@/config';
import type { UserInputEnvelope } from '@/types/envelope';
import type { SSEEvent } from '@/types/chat';

// 删除 createSession() — session 由 background 创建

export async function sendEnvelope(sessionId: string, env: UserInputEnvelope): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/session/${sessionId}/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ envelope: env }),
  });
  if (!res.ok) throw new Error('Failed to send envelope');
}

export function connectSSE(
  sessionId: string,
  onEvent: (e: SSEEvent) => void,
  onError?: () => void,
): () => void {
  const es = new EventSource(`${API_BASE_URL}/api/session/${sessionId}/events`);
  // ... 与 web/sseClient.ts 一致
  return () => es.close();
}
```

**关键差异**（与 `web/sseClient.ts`）：
- URL 用绝对地址 `${API_BASE_URL}/api/...`
- 新增 `sendEnvelope` 替代 `sendMessage`，body 为 `{ envelope }` 而非 `{ text }`
- 移除 `createSession`（由 background 通过 `backgroundClient.getSession()` 处理）

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
      kind: 'web',
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
3. `buildEnvelope` source.surface='sidecar'

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
cd extension
npm run build  # tsc 类型检查 + vite build
# 产物在 extension/dist/
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

### Step 6: 占位图标
- 生成 3 个占位 PNG（16/48/128）

### Step 7: README
- 写 `extension/README.md`（§12 开发与构建流程）
