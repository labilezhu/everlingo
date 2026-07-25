# Web Chatbot

Web 前端给用户，一个 Chatbot 的聊天界面。支持 markdown 格式消息的渲染。

成功连接 Chatbot 后端后，session id 将作为前后端建立连接时的标识。

前端代码，静态网页文件位于目录 `/web` 中。

## 同步修改 Web Chatbot

每次修改 Web Chatbot 时，都需要考虑是否同步修改功能相近的 [Chrome Extension — Web Sidecar](docs/impl-spec/chrome-extension-spec.md)。

## 通用界面设计风格
尺寸大小：
- 主可视区域的宽度，应该跟随窗口大小的动态变化动态调整，以最大化用户的可视区域。左右边缘适当留白即可。

## Chatbot 界面设计
一个经典的 chatbot 聊天对话框。聊天机器人的名字叫：小记🐹 

消息内容主要是 markdown 文本，markdown 文本消息需要在界面渲染。

### Header

全窗口模式（非 embedded）下，header 右侧显示「笔记编辑器」按钮，点击同窗跳转至 `/editor`（[Vault Editor](vault-editor.md) 入口）。embedded 模式（editor 右侧侧栏）下不显示该按钮。

小记🐹正在思考的提示：
- 在用户发送消息后，“发送” 按钮变为一个轻微的脉冲动画以提示"正在思考中"。在收到回复消息后还原。不要使用现有的前端的 thinking 机制。

尺寸大小：
- Chatbot 对话框可视区域的宽度，应该跟随窗口大小的动态变化动态调整，以最大化用户的可视区域。左右边缘适当留白即可。

### 任务选择（task selector）

header 下方有一行 button group（三个 `Button` 组件，选中态 `variant=default`、未选态 `variant=outline`），与 [Chrome Extension sidecar](chrome-extension-spec.md) 的 `TaskSelector` 视觉一致。

让用户表达输入内容的意图：

| 按钮 | `task` 值 | 说明 |
|---|---|---|
| 翻译 | `translate` | 翻译选词或输入的句子 |
| 查词 | `look_up` | 查询单词释义 |
| 聊天 | `none` | 自由聊天，默认选中 |

选择在组件内持久化（直到用户手动切换），每条消息发送时携带当前 task。

task 语义遵循 [chrome-extension-spec.md §8](chrome-extension-spec.md) 的定义——**用户偏好而非 RPC 命令**，Agent 可自由决定是否遵循。

### 交互元素
“发送” 按钮：
“发送” 按钮应该调整为更大。上面应该有文字和一个代表 “发送” 的简单 SVG 图形，类似 ➡️。

消息内容的 Markdown 渲染：
默认的文字行距太小，需要加倍。

### 消息内链接点击行为

消息内容中的 markdown 链接由 `react-markdown` 渲染为 `<a>`，默认 `target="_blank" rel="noopener noreferrer"`（新 Tab 打开）。

当 chatbot 被嵌入到其它应用（如 [Vault Editor](vault-editor.md) 右侧侧栏）时，宿主可通过 `ChatWindow` 的 `linkListener?: (url: string) => boolean` prop 接管链接点击：

- 点击时先调用 `linkListener(url)`
- 返回 `true`：chatbot 不再处理（`preventDefault`），由宿主自行处理（如同窗打开文件）
- 返回 `false`：回退默认行为（新 Tab 打开）

### Envelope 字段填充规则

Standalone Web Chatbot 切换到结构化 `{envelope}` 格式发送消息（不再使用 `{text}` legacy 格式）。字段填充规则：

| 字段 | 填充来源 |
|---|---|
| `schema_version` | 固定 `1` |
| `task` | TaskSelector button group 选择 |
| `chat.message` | 输入框文本 |
| `selection.text` | `""`（web chatbot 无选词场景） |
| `context.text` | `""` |
| `source.kind` | `"web"` |
| `source.surface` | `"fullscreen"`（与 sidecar 的 `"sidecar"` 区分） |
| `source.url` | `window.location.href` |
| `source.title` | `document.title` |
| `device.platform` | `"web"` |
| `device.locale` | `navigator.language` |
| `device.timezone` | `Intl.DateTimeFormat().resolvedOptions().timeZone` |

`selection.text` / `context.text` 留空，因为 standalone web chatbot 没有页面选词上下文。

### 示例

用户打开聊天页面，选择「翻译」，输入 "bank is a financial institution"：

```json
{
  "envelope": {
    "schema_version": 1,
    "task": "translate",
    "chat": { "message": "bank is a financial institution" },
    "selection": { "text": "" },
    "context": { "text": "" },
    "source": {
      "kind": "web",
      "surface": "fullscreen",
      "url": "http://localhost:5173/",
      "title": "小记🐹 AI 外语老师"
    },
    "device": {
      "platform": "web",
      "locale": "zh-CN",
      "timezone": "Asia/Shanghai"
    }
  }
}
```


## 前端技术选型

使用组件库:
- Vite
- React
- TailwindCSS
- shadcn/ui
- react-markdown

### Vite 
用途
项目构建工具（开发服务器 + 打包工具）。

负责:
项目创建
本地开发服务器
热更新（HMR）
生产环境打包

作用范围，仅负责：
开发
构建
打包

不负责：
UI
聊天
Markdown
SSE

### React
用途：
前端 UI 框架。

负责：
页面状态管理
聊天消息列表
输入框
页面布局
SSE 消息事件处理

推荐组件结构：
```
src/

components/

  ChatWindow.tsx
  MessageBubble.tsx
  MarkdownRenderer.tsx
  ChatInput.tsx

services/
  sseClient.ts

types/
  chat.ts
```

### TailwindCSS
用途:
CSS 样式框架。

负责：
布局
颜色
边距
字体
响应式设计

用于:
聊天窗口：
左右布局
消息气泡
输入框样式
滚动区域

不负责:
组件逻辑
Markdown
SSE

### shadcn/ui
通用 UI 组件库。
基于：

TailwindCSS
+
Radix UI

生成源码到项目中。不是运行时依赖。

负责：
- Button
- Input
- Textarea

### react-markdown

用途

渲染 AI 返回的 Markdown。

### SSE 自动重连

连接不稳定（尤其移动端）时，SSE 断线后自动重连，无需用户刷新页面。

**重连策略**（`sseClient.ts:connectSSE`）：
- `onerror` 触发时检查 `es.readyState`：
  - `CLOSED`（服务器返回非 200 响应，如 404 session 已过期）→ 进入 `session_expired` 态，不再重试。
  - `CONNECTING`（网络中断）→ 关闭当前 `EventSource`，接管重连控制。
- 指数退避：1s → 2s → 4s → 8s → 16s → 30s（封顶 30s），无限重试。
- 重连期间通过 `onStatus` 回调通知组件当前状态（`reconnecting` + 倒计时秒数）。
- 暴露 `retryNow()` 方法供 UI「立即重试」按钮跳过等待直接重试。
- 重连成功后（`onopen` 触发）回调 `onStatus({ state: 'connected' })，状态归零。

**UI 表现**（`ChatWindow.tsx`）：
- `connStatus.state === 'reconnecting'`：TaskSelector 下方显示 amber 色提示条：
  `连接断开，{N}s 后自动重试 [立即重试]`
- `connStatus.state === 'session_expired'`：amber 色提示条：
  `会话已过期 [重新开始]`
  - 点击「重新开始」→ `handleRebuild()`：创建新 session + 连接新 SSE + 在消息列表插入灰色系统通知「小记已重新开始，之前的对话记忆已丢失」。
  - UI 历史消息保留可见，但 Agent 上下文已重置。
- 正常连接、重连成功后，不显示任何提示信息。
- 非连接类错误（如"发送消息失败"）保持红色 error banner，与连接状态分离管理。

### Favicon

使用 `web/public/favicon.png`（源图 `docs/arts/chrome-icon.png`），通过 Vite `public/` 约定自动拷贝到构建产物根目录。两个 web 入口（chatbot + editor）共用同一 favicon，均在 `<head>` 以 `<link rel="icon" type="image/png" href="/favicon.png" />` 引用。后端由 `web_acceptor.py` catch-all 路由 `GET /favicon.png` → `web/dist/favicon.png`。

## 移动端适配

以 Tailwind 默认 `md` 断点（768px）为界。所有响应式差异用 `md:` 前缀表达，不引入 `useMediaQuery`（chatbot 单栏纵向布局无需 JS 状态切换、无抽屉、无 backdrop）。

### 断点
`md` (768px)。所有响应式类使用 `md:` 前缀。

### 按钮文字标签自适应隐藏
「图标 + 文字」按钮的文字用 `<span className="hidden md:inline">` 包裹，图标常驻。`< md` 只显示图标，`>= md` 显示完整文字。涉及：

| 位置 | 按钮 | 文件:行 |
|------|------|---------|
| Header | 笔记编辑器 | `ChatWindow.tsx` |
| Input | 发送 | `ChatInput.tsx` |

「发送」按钮在移动端额外收紧为方形 icon button（`w-9` + `aria-label="发送"`），桌面恢复 auto 宽度。

`TaskSelector` 的「翻译/查词/聊天」是纯文字按钮（无图标），保持不动——2 字标签在 iPhone 上放得下，隐藏反而损害可用性。

### 容器 padding / border 响应式
- `ChatWindow` 根 `px-0 md:px-6 border-x-0 md:border-x`：移动端全屏贴边，桌面保留装饰边框 + 24px 留白。
- Header / messages / ChatInput form 的 `px-4 py-3` → `px-3 py-2 md:px-4 md:py-3`。

### 不在本范围
- 不引入抽屉 / backdrop / `useMediaQuery`（chatbot 无此需求）。
- 不改 SSE / session / envelope 逻辑。
- Chrome Extension Web Sidecar（`extension/src/components/`）是独立代码副本，且 sidecar 仅在桌面浏览器 Chrome side panel 中运行，移动端适配不适用，无需同步修改。
