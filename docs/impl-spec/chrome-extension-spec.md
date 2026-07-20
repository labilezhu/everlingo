# Chrome Extension — Web Sidecar

- 状态：Planned（2026-07）
- 阶段：Phase 2
- 相关文档：
  - [Envelope 结构化用户输入协议](envelope-spec.md)
  - [Web Session Acceptor](web-session-acceptor.md)
  - [Web Session UI - Web Chatbox Web UI](web-session-ui.md)
  - [Chat Agent](chat-agent-spec.md)
  - [Channel](channel.md)
  - [Session](session.md)
  - [产品说明 - phase 2](../phases/phase2/product-phase-2.md)

---

## 1. 背景与目标

EverLingo 产品定位是"有记忆的 AI 外语老师"，核心创新是把"查询行为"转化为"学习资产"。浏览器是用户最高频发生查询行为的场景，Chrome Extension 是把"选词 → 翻译 → 记录场景"串起来的物理载体，也是 [PRODUCT-FUNC.md](/PRODUCT-FUNC.md) "使用方便" 一节明确列出的整合目标。

Envelope 协议在设计时已为 Chrome Extension 预留了 `source.kind="web"`（见 [envelope-spec.md §source tagged union](envelope-spec.md)），本 feature 是 envelope 协议落地的第一个真实场景。后端复用现有 `WebSessionAcceptor` + `WebChannel` + `Session` + `ChatAgent` 链路，**后端代码零改动**（envelope schema 的小幅扩展除外）。

### MVP 范围

- 用户在任意网页点击扩展图标 → 打开右侧 sidecar panel
- sidecar 内是一个 chatbot 界面（复用 `web/src/components/`）
- 自动注入 envelope：`task=translate` / `look_up`，携带 `selection.text` 与 `context.text`
- Agent 翻译选词，并支持在 sidecar 内通过聊天完成笔记记录
- 同一 tab 内 sidecar 隐藏后，二次激活在 20 分钟内复用原 session
- sidecar 仅在用户激活过扩展的 tab 上显示；切换到未激活 tab 时自动隐藏，切回已激活 tab 时自动显示，React 应用实例与 session 状态保留

### MVP 不做

- 选词后自动弹翻译小工具图标（需 `host_permissions`，审核与体验成本高，后续再做）
- 屏幕截图（envelope schema 已预留 `context.screenshot` 字段，未来实现）
- 鉴权（后端 web_acceptor 暂不校验 origin，未来加 extension_id 白名单或一次性 token）
- 跨 tab 共享 session
- 浏览器重启后恢复 session

---

## 2. 架构总览

```
Chrome Extension (extension/ 子目录)
  ├─ manifest (MV3)
  ├─ background service worker
  │    └─ 管理 tab → session_id 映射
  ├─ sidecar panel (chrome.sidePanel)
  │    └─ React app（复用 web/src/components/）
  └─ (未来) content script — 选词弹图标
        ↓ HTTPS
WebSessionAcceptor (已有 FastAPI, web_acceptor.py)
  ├─ POST /api/session              ← 扩展调，创建 session
  ├─ POST /api/session/{id}/message ← 扩展调，发 envelope
  └─ GET  /api/session/{id}/events  ← 扩展调，SSE 接收回复
        ↓
WebChannel → Session → MainAgent (Chat Agent)
```

数据流复用 envelope-spec.md §数据流 与 web-session-acceptor.md 已定义的协议，扩展仅作为新的前端客户端。

---

## 3. 代码位置

Chrome Extension 代码位于 `/home/labile/everlingo/extension/` 子目录，与 `web/` 平级，与主 repo 共享 git 历史（非 submodule）。

```
everlingo/
├─ web/           # 现有 web chatbot 前端
├─ extension/     # Chrome Extension（本 feature）
│   ├─ manifest.json
│   ├─ package.json
│   ├─ vite.config.ts
│   ├─ src/
│   │   ├─ background.ts
│   │   ├─ Sidecar.tsx
│   │   └─ components/  # 拷贝自 web/src/components/，独立维护
│   └─ ...
└─ src/everlingo/  # 后端
```

**组件复用策略**：从 `web/src/components/` 拷贝 `ChatWindow` / `MessageBubble` / `ChatInput` / `MarkdownRenderer` 到 `extension/src/components/`，独立维护。理由：

- Chrome Extension 与 web chatbot 的布局约束不同（sidecar 固定窄宽度 vs web 全屏自适应），组件演进方向会逐渐分歧
- 避免引入 monorepo 工具（如 pnpm workspace）增加工程复杂度
- 后续若分歧过大，可平滑迁移为独立 git repo

---

## 4. 权限（MVP）

`manifest.json` 申请最小权限集：

| 权限 | 用途 |
|---|---|
| `activeTab` | 用户主动点扩展图标时获取当前 tab 信息（url/title），不需要 `host_permissions` |
| `sidePanel` | 使用 `chrome.sidePanel` API 打开右侧 panel（Chrome 114+） |
| `storage` | 持久化 `device_id`（`chrome.storage.local`）、`server_url`（`chrome.storage.local`）与 tab → session_id 映射（`chrome.storage.session`） |
| `contextMenus` | 选中文本后，右键菜单显示"用小记🐹翻译"入口 |

**不申请** `host_permissions`：MVP 不实现"选词后自动弹翻译小工具图标"。用户必须通过扩展图标或右键菜单激活翻译，激活后从 `chrome.tabs.query({active:true})` 读取当前 tab 的 url/title，以及通过 `chrome.scripting.executeScript` 在页面执行脚本取 `window.getSelection().toString()` 与上下文。

---

## 5. Session 生命周期

### 5.1 标识

| 标识 | 作用域 | 生成时机 | 存储 |
|---|---|---|---|
| `device_id` | 跨 tab、跨浏览器重启持久 | 扩展安装时（uuid v4） | `chrome.storage.local` |
| `session_id` | 单 tab 内 | 首次激活 sidecar 时（后端 `POST /api/session` 返回） | `chrome.storage.session`（浏览器关闭即失效） |
| `tabId` | 浏览器内 | Chrome 自动分配 | 仅作为 `chrome.storage.session` 的 key 前缀 |

`device_id` 与 envelope 的 `device.device_id` 字段对应，用于跨 tab 聚合用户档案（USER.md）；`session_id` 按 tab 维度独立，避免多 tab 同时操作互相串扰。

### 5.2 Sidecar 打开流程

sessionId 由 sidecar panel 启动后主动向 background 查询，**不**通过 URL query 传递。所有 session 创建/复用/超时探活逻辑集中在 background service worker 的消息处理函数中，sidecar panel 职责单一：启动 → 恢复 UI history → 查 session → 连 SSE → 发 envelope。

```
扩展安装时（onInstalled）:
  0. chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true })
     全局 panel：点图标 toggle 显示/隐藏，切 tab 时 panel 保持显示

用户点扩展图标
  ↓
（Chrome 自动 toggle side panel，不再触发 action.onClicked）
  ↓
sidecar panel (React app) 启动 / 恢复:
  1. 若首次启动，读 chrome.storage.local 获取 device_id + apiBaseUrl
  2a. 从 chrome.storage.session 读取 msgs:${tabId}，恢复 UI message history
  2b. 通过 chrome.runtime.sendMessage({ type: "GET_SESSION" })
      向 background 询问 sessionId
  ↓
background 收到 GET_SESSION 消息:
  3. tabId = (await chrome.tabs.query({active:true}))[0].id
  4. sessionId = await chrome.storage.session.get(`sid:${tabId}`)
  5. 若有 sessionId → GET /api/session/{id}/events (SSE 探活)
      ├─ 200 → 复用，返回 { sessionId, fresh: false }
      └─ 404 → 走新建流程
  6. 若无或 404:
     - chrome.storage.session.remove(`msgs:${tabId}`)  ← 清理旧 UI history
     - POST /api/session  →  拿到新 sessionId
     - chrome.storage.session.set(`sid:${tabId}`, sessionId)
     - 返回 { sessionId, fresh: true }
  ↓
sidecar panel 收到响应:
  7. 若 fresh=true → 清空 UI（与 storage 已被 background 清除同步）
  8. 建立 SSE 连接
  9. 构造首次 envelope（含 selection/context/source/device）
  10. POST /api/session/{id}/message { envelope: {...} }
  ↓
  11. 注册 chrome.tabs.onActivated 监听：切 tab 时自动重复步骤 2a-8
      （不 capture snapshot，不 auto-send，避免权限与打扰问题）
```

**设计要点**：

- **不在打开 sidecar 前预创建 session**：避免用户立即关闭 sidecar 产生孤儿 session（session 已在后端建立却无人连接）。改为 sidecar 启动后主动查询，session 创建与 sidecar 实际使用绑定。
- **session 管理集中在 background**：sidecar panel 不直接读写 `chrome.storage.session` 的 `sid:${tabId}`，session 状态由 background 统一管理（UI history 的读写见 §7.4）。
- **全局 panel + tab 切换刷新内容**：`setPanelBehavior({ openPanelOnActionClick: true })` 使 panel 全局化——点图标 toggle，切 tab 时 panel 保持显示。sidecar 监听 `chrome.tabs.onActivated`，切 tab 时自动调用 `switchToTab()`：关旧 SSE → 查新 tab session → 加载 UI history → 连新 SSE。不同 tab 的 sidecar 状态互相隔离，切换不串扰。切 tab 时不 capture snapshot 也不 auto-send（因无 `activeTab` 授权 + 避免频繁打扰）。
- **UI history 与 Agent 上下文同步**：session 重建时 background 先 `remove(msgs:${tabId})` 再返回 `fresh=true`，sidecar 据此清空 UI，避免"UI 有历史但 Agent 不记得"的错配。详见 §7.4。

### 5.3 隐藏与二次激活

#### 5.3.1 Tab 切换（panel 保持显示，内容刷新）

- `setPanelBehavior({ openPanelOnActionClick: true })` 使 panel 全局化——切 tab 时 panel **保持显示**，不隐藏
- sidecar React 应用监听 `chrome.tabs.onActivated`（带 `windowId` 过滤，仅响应本窗口切换），切 tab 时自动执行 `switchToTab()` 流程：
  - 关旧 SSE → 查新 tab session → 加载 UI history → 连新 SSE
- 切 tab 时不 capture snapshot（因新 tab 无 `activeTab` 授权）、不 auto-send envelope（避免频繁打扰）
- 不同 tab 的 sidecar 状态互相隔离：tab A 与 tab B 各自维护独立的 `sid:${tabId}` 与 `msgs:${tabId}`，切换不串扰
- 用户如需主动触发翻译，使用右键菜单"用小记🐹翻译"——background 收到后 `open({ tabId })`（打开全局 panel）并发送 `TRIGGER_TRANSLATE` 消息，sidecar 收到后 capture snapshot + send envelope

#### 5.3.2 用户主动关闭 panel 后的二次激活

- Sidecar 隐藏（失焦、点关闭）→ 前端关闭 SSE 连接
- 后端 `WebChannel` 检测到 `len(_sse_queues)==0`，进入 `DISCONNECT_GRACE` 倒计时
- 二次激活同 tab：
  - **20 分钟内（session 仍在）**：sidecar panel 启动 → 从 `chrome.storage.session` 读 `msgs:${tabId}` 恢复 UI history → 向 background 查询 sessionId → `GET /api/session/{id}/events` 探活返回 200 → background 返回 `{ sessionId, fresh: false }` → sidecar 不清空 UI，直接连 SSE。**Agent 上下文保留 + UI history 恢复，体验连续。**
  - **超过 20 分钟（session 已被后端回收）**：`recv_envelope()` 返回 `None` → `QuitEvent` → Gateway 从 Session 列表移除。sidecar 查询时探活返回 404 → background 走新建流程：`remove(msgs:${tabId})` 清除旧 UI history → `POST /api/session` 拿新 sessionId → 返回 `{ sessionId, fresh: true }` → sidecar 据此清空 UI。**UI history 与 Agent 上下文同步丢失，不会错配。**

### 5.4 超时配置

`WebChannel.DISCONNECT_GRACE` 由 5 分钟调整为 **20 分钟**（1200 秒），适配 sidecar 频繁隐藏/激活的使用模式。`ABSOLUTE_IDLE_TIMEOUT`（60 分钟）保持不变。

详见 [web-session-acceptor.md — Session 超时回收](web-session-acceptor.md)。

### 5.5 边界

- **不支持跨 tab 共享 session**：每个 tab 独立 session（`sid:${tabId}` 隔离），切换 tab 时 sidecar 显示对应 tab 的 session 内容，避免多 tab 同时操作时 Agent 上下文混淆
- **不支持浏览器重启恢复 session**：`chrome.storage.session` 在浏览器关闭时清空（`sid:${tabId}` 与 `msgs:${tabId}` 一并消失），重启后所有 tab 都需新建 session
- **接受会话丢失**：20 分钟超时后新建 session，UI history 与 Agent 上下文同步丢失。未来优化方向见 §10

---

## 6. Envelope 构造

扩展在 sidecar 打开后，按下述规则构造 `UserInputEnvelope` 并 `POST /api/session/{id}/message`。

### 6.1 字段填充规则

| 字段 | 填充来源 |
|---|---|
| `schema_version` | 固定 `1` |
| `task` | UI 按钮决定：`translate` / `look_up` / `none`（自由聊天） |
| `chat.message` | 用户在 sidecar 输入框的文字（首次激活可能为空） |
| `selection.text` | `window.getSelection().toString()`（通过 `chrome.scripting.executeScript` 在页面上下文执行） |
| `context.text` | 见 §6.3 算法（同样通过 `chrome.scripting.executeScript` 在页面上下文执行） |
| `context.screenshot` | **MVP 不填**（schema 已预留，未来用 `chrome.tabs.captureVisibleTab` 填） |
| `source.kind` | `"web"` |
| `source.surface` | `"sidecar"` |
| `source.url` | `chrome.tabs.query({active:true})` 返回的 Tab 对象的 `url` 字段 |
| `source.title` | `chrome.tabs.query({active:true})` 返回的 Tab 对象的 `title` 字段 |
| `device.platform` | `"chrome_ext"` |
| `device.device_id` | `chrome.storage.local.device_id` |
| `device.locale` | `navigator.language`（sidecar panel 自身上下文即可取） |
| `device.timezone` | `Intl.DateTimeFormat().resolvedOptions().timeZone`（sidecar panel 自身上下文即可取） |

### 6.2 `source.surface` 枚举

| 值 | 含义 |
|---|---|
| `sidecar` | 浏览器右侧栏 panel（本 feature MVP 形态） |
| `popup` | 独立弹窗（未来） |
| `fullscreen` | 整页 web chatbot（即现有 `web/` 前端） |

`SourceWeb.surface` 默认值为 `"fullscreen"`，使现有 web chatbot 发的 envelope（若未来也用 `source.kind=web`）与 Chrome Extension sidecar 天然区分。当前 web chatbot 仍发 `source.kind=plain`（见 [envelope-spec.md §6](envelope-spec.md)），surface 默认值不影响现有行为。

### 6.3 `context.text` 提取算法

目标：取选词所在段落的文本，最多 500 字，用于消歧（如 `bank` 在河岸 vs 银行）。

```
function extractContextText(selection: Selection): string {
  if (!selection.rangeCount) return "";
  const range = selection.getRangeAt(0);
  let block = range.commonAncestorContainer as Element | null;
  // 从选区公共祖先向上找最近的 block-level 元素
  while (block && !isBlockElement(block)) {
    block = block.parentElement;
  }
  if (block) {
    const text = block.textContent || "";
    return text.length > 500 ? text.slice(0, 500) : text;
  }
  // 回退：选区前后各 250 字
  const fullText = document.body.innerText;
  const start = Math.max(0, range.startOffset - 250);
  return fullText.slice(start, start + 500);
}

function isBlockElement(el: Element | null): boolean {
  if (!el || !el.tagName) return false;
  const tag = el.tagName.toUpperCase();
  return ["P","DIV","SECTION","ARTICLE","LI","H1","H2","H3","H4","H5","H6","BLOCKQUOTE","PRE","TD"].includes(tag);
}
```

### 6.4 示例

用户在 `https://example.com/article` 选中 `bank`，点击扩展图标 → sidecar 打开 → 默认 `task=translate`，首次消息为空：

```json
{
  "schema_version": 1,
  "task": "translate",
  "chat": { "message": "" },
  "selection": { "text": "bank" },
  "context": { "text": "I sat on the bank of the river.", "kind": "paragraph" },
  "source": {
    "kind": "web",
    "surface": "sidecar",
    "url": "https://example.com/article",
    "title": "Example Article"
  },
  "device": {
    "platform": "chrome_ext",
    "device_id": "550e8400-e29b-41d4-a716-446655440000",
    "locale": "zh-CN",
    "timezone": "Asia/Shanghai"
  }
}
```

---

## 7. Sidecar UI

### 7.1 布局

- 固定窄宽度：约 380px（Chrome sidePanel 默认宽度）
- 复用 [web-session-ui.md](web-session-ui.md) 的设计规范：Chatbot 名"小记🐹"、markdown 渲染、发送按钮脉冲动画等
- 与 `web/` chatbox 的差异：不跟随窗口宽度动态调整（sidecar 宽度由 Chrome 决定）

### 7.2 交互

- sidecar 打开后，若检测到 `selection.text` 非空 → 自动用首次构造的 envelope 发起一次请求（即使用户没在输入框输入文字）；若 `selection.text` 为空 → 不自动发起请求，仅显示输入框等待用户操作
- 顶部有 task 切换按钮：翻译 / 查词 / 自由聊天
- 用户在输入框继续追问时，`task` 保持当前选择，`selection`/`context` 字段保留为**本次 per-tab 激活周期内**的快照（不重新抓取），`chat.message` 为用户新输入
- 二次激活（隐藏后重新打开，或 tab 切换后 Chrome 重建 panel）视为新的"激活周期"：重新抓取 selection/context，按上一条规则决定是否自动发起请求
- Agent 回复通过 SSE 推送，前端渲染为消息气泡
- **UI message history 持久化**：sidecar 每发送一条 user message、每收到一条 SSE `message` 事件时，均 append 到 `chrome.storage.session` 的 `msgs:${tabId}`（详见 §7.4）。sidecar 启动时先读 storage 恢复 UI history，再向 background 查询 session。这样 sidecar 隐藏/重开 20 分钟内可恢复完整聊天记录。

### 7.3 技术栈

复用 [web-session-ui.md — 前端技术选型](web-session-ui.md)：Vite + React + TailwindCSS + shadcn/ui + react-markdown。打包为 CRX 时用 `@crxjs/vite-plugin` 或类似工具。

### 7.4 UI message history 持久化

sidecar panel 关闭后 React 组件被 Chrome 销毁，本地 state 丢失；重新打开时若仅恢复 sessionId 而不恢复 UI history，会出现"Agent 记得但 UI 空白"的体验割裂。本节定义 UI history 的客户端持久化方案。

**存储位置**：`chrome.storage.session`，key 为 `msgs:${tabId}`（与 `sid:${tabId}` 同源存储）。

**value 格式**：

```typescript
type UIMessageRecord = {
  role: "user" | "assistant";
  text: string;
  timestamp: string;  // SSE 事件已有的 timestamp 字段，同时作为去重 key
};
type MsgsStorageValue = UIMessageRecord[];
```

**写入时机**：

- sidecar 发送 user message（`POST /api/session/{id}/message`）成功后，append 一条 `{role:"user", ...}`
- sidecar 收到 SSE `message` 事件时，append 一条 `{role:"assistant", ...}`，用事件 `timestamp` 去重（避免 SSE 重连重复推送导致重复 append）

**读取时机**：

- sidecar panel 启动时（§5.2 步骤 2a），先于 GET_SESSION 查询

**清除时机**：

- background 在 §5.2 步骤 6 检测到 404 走新建流程时，先 `chrome.storage.session.remove(`msgs:${tabId}`)` 清除旧 history，再返回 `fresh: true`，sidecar 据此同步清空 UI

**容量与淘汰**：

- `chrome.storage.session` 单项限制 10MB，聊天文本场景足够
- 超出时按 FIFO 丢头部最旧消息（实现时通过 `storage.getBytesInUse` 监控）

**生命周期对齐**：

- `chrome.storage.session` 浏览器关闭即清空，与 `sid:${tabId}` 同源，不会出现"UI history 还在但 session 已销毁"或"session 还在但 UI history 没了"的错配

**与笔记落盘解耦**：

- UI history 仅用于渲染，不作为知识沉淀的事实源
- 真正的笔记落盘走 Agent 的 `request_memory_extraction` 流程（见 [chat-agent-spec.md — 记忆抽取触发](chat-agent-spec.md)），两条路径不互相依赖

---

## 8. `task` 语义（与 Agent 的契约）

`task` 是**用户偏好**，不是 RPC 命令（见 [envelope-spec.md §字段说明](envelope-spec.md) 与 [chat-agent-spec.md — 结构化用户输入](chat-agent-spec.md)）。Agent 可自由决定是否遵循：

- `task=translate`，用户追问"顺便解释一下为什么这里用 bank" → Agent 先翻译，再解释
- `task=look_up`，用户输入为空 → Agent 视为"延续上一轮笔记话题"，不要回复"未收到输入"，应基于对话历史继续推进相关工作（如读取/编辑上一轮提到的笔记）

`task=look_up` + 空输入的延续语义规则需在 `chat-agent-spec.md` 与 `agent.py` system prompt 的 `## 结构化用户输入（envelope）` 节中明确写入。

---

## 9. 鉴权（MVP 不做）

- 后端 `web_acceptor.py` 暂不校验 origin
- Chrome Extension origin 形如 `chrome-extension://{extension_id}`，未来可在 FastAPI 中间件加白名单
- 更完善方案：扩展启动时 `POST /api/device/register` 拿一次性 token，后续请求带 token

---

## 10. 未来优化方向

- **选词自动弹图标**：申请 `host_permissions` + content script 监听 `mouseup`，仿 Google Translate Extension 体验（当前已通过右键菜单 + 扩展图标点击实现翻译触发，用户可主动调起）
- **截图记忆锚点**：实现 `chrome.tabs.captureVisibleTab` 填充 `context.screenshot`，对齐 [product-phase-2.md](../phases/phase2/product-phase-2.md) 的"原屏幕截图"目标
- **Session 持久化**：`Session` 对话历史落盘（[session.md](session.md) 明确"暂时不需要支持持久化"），支持浏览器重启后恢复
- **服务端 message history API 作为权威源**：当前方案 B（§7.4）依赖 client storage，未来可加 `GET /api/session/{id}/messages?since=<seq>` 作为单一事实源，解决多设备/多 sidecar 实例同步问题
- **跨 tab 共享 session**：当前 sidecar 切换 tab 时各 tab 独立 session（§5.5），未来可支持用户主动合并多 tab 对话上下文
- **鉴权**：extension_id 白名单 或 一次性 token
- **PDF / EPUB 阅读器内嵌**：复用 envelope `source.kind=pdf` / `epub` 预留字段
