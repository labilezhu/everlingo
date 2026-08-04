# Vault Editor

Web 前端给用户一个可视化编辑 [Memory Vault](/src/everlingo/mem/vault/templates/default/spec/vault_spec.md) 中 markdown 文件的编辑器。支持 源码 / 直观 双模式切换、文件树浏览、搜索。

编辑器入口 URL：`http://localhost:8000/editor`。

与 [Standalone Web Chatbot](/docs/impl-spec/web-chatbot.md) 共用同一 HTTP server（[Web Session Acceptor](/docs/impl-spec/web-session-acceptor.md)），同一 origin，不同前端入口。前端代码位于同一 Vite 工程 `/web`，多入口构建。

## 通用界面设计风格
沿用 [Standalone Web Chatbot §通用界面设计风格](/docs/impl-spec/web-chatbot.md)：主可视区域宽度跟随窗口动态调整，左右边缘适当留白。

## 编辑器界面设计

三栏布局：

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Header：lang selector  |  🐹 小记笔记编辑器  |  模式切换  |  呼叫小记  |  转到小记  |  保存  │
├──────────┬──────────────────────────────────┬──────────────────────────────────┤
│          │                                   │                                  │
│  文件树  │           编辑区（Milkdown）       │    小记🐹 Chatbot 侧栏           │
│  / 搜索  │                                   │   (可调宽, 常驻 session)         │
│ (可调宽) │                                   │                                  │
└──────────┴──────────────────────────────────┴──────────────────────────────────┘
```

左栏宽度可调。两栏之间有一个 4px 拖拽手柄，hover 时变色并显示 `col-resize` 光标。拖拽通过 Pointer Events 实现，宽度按百分比记录到 localStorage（key `vault-editor:leftPanePct`，默认 22%，范围 15%-50%）。刷新/重开页面后恢复。

### Header

- **lang selector**：单选下拉，候选项来自 `GET /api/vault/langs`（底层 MCP `list_vaults`）。切换 lang 重新拉取文件树。未传 `?lang=` 时默认选中 `everlingo.yaml` 中 `user_profile.language.target_language` 配置的默认目标学习语言（若该 lang 不在 vaults 列表中则回退到列表第一项）；`default` 字段随 `GET /api/vault/langs` 响应返回。
- **模式切换**：源码 / 直观 两态 toggle，组件内持久化。
- **呼叫小记**：toggle 按钮。首次按下时在右侧挂载 chatbot 侧栏（`ChatWindow` 组件，建 session + 连 SSE）；再次按下只 CSS 隐藏侧栏，**不卸载组件**（session 与 SSE 保持，下次打开延续会话）。选中态高亮 `bg-primary text-primary-foreground`。
- **转到小记**：`window.location.href = '/'`，同窗跳转到 [Standalone Web Chatbot](web-chatbot.md) 独立入口。
- **保存**：将当前编辑器内容 `POST /api/vault/{lang}/write`。未改动时禁用；改动未保存时按钮高亮 + 关闭/切文件前 confirm。

#### 右侧 Chatbot 侧栏

编辑器 body 区采用四栏布局（上图），最右侧为 chatbot 侧栏：

- 组件直接复用 `ChatWindow`（来自 `@/components/ChatWindow`），其根节点 `h-full` 以适配 flex 子元素高度。
- 首按「呼叫小记」时 `chatMounted=true`，组件常驻挂载；后续 toggle 仅通过 `hidden` class 控制显隐，session 与 SSE 持续保持。
- 左边缘 4px 拖拽手柄（`cursor-col-resize`，Pointer Events），与左栏拖拽同模式。宽度按百分比记录到 localStorage（key `vault-editor:chatPanePct`，默认 32%，范围 20%–50%）。刷新/重开页面后恢复。

### 文件树（FileTree）

- 数据源：`GET /api/vault/{lang}/tree`（底层 MCP `tree`）。
- 树形展开/折叠，点击文件 → 加载到编辑区。
- 显示名规则：
  - 文件：取 entry 的 `title`（来自 frontmatter）。`title` 缺省/空 → 回退文件名。例外：`index.md` 永远显示 `index.md`（但其 frontmatter `title` 用作所在目录的显示名）。
  - 目录：取该目录下 `index.md` 的 frontmatter `title`。无 `index.md` 或 `title` 缺省/空 → 回退目录名。
- 子目录懒加载：首次展开 children 为空的目录时，按需调用 `tree(path=<dir>, depth=2)` 拉取该目录的子项并合并到树状态。已加载的目录再次折叠/展开不重复请求。
- 右键菜单 / 顶部按钮组：
  - 新建文件（输入 path，自动 `.md` 后缀）
  - 新建目录
  - 重命名（MVP 走 read+write+delete 复合，见下「后端 REST 端点」）
  - 删除
- **`tmp/` 目录默认隐藏**；顶部 toggle「显示隐藏目录」可切换。`tmp/` 不入索引（见 [vault-mcp-spec.md](/docs/impl-spec/vault-mcp/vault-mcp-spec.md)「`spec/` 目录不入索引」段的 `is_excluded_vault_file` 描述）。OS 隐藏文件/目录（name 以 `.` 开头，如 `.git`/`.obsidian`/`.DS_Store`）后端 `tree` 端点默认硬过滤，无 toggle。
- `spec/` 目录允许编辑（与其它目录同权）。
- 文件树顶部有 header 工具栏（初始仅含刷新按钮）：刷新触发整树重拉（`tree(selectedLang)`），懒加载状态重置；不影响编辑器内容与未保存改动。

### 搜索（SearchBar）

左栏采用 Files / Search **Tab 切换**（互斥；`hidden` CSS 保留各自状态以维持滚动位置和输入内容）。URL 带 `q` 参数时初始进入 Search tab；否则优先读 localStorage（key `vault-editor:leftTab`），缺省 Files。

- 搜索框（`<Input>`）+ Enter / 按钮触发。
- 模式选择：hybrid / exact / semantic 三态 `<Button>` toggle（默认 hybrid），按钮显示中文标签：混合 / 精确 / 语义，行首标注"搜索模式："。`q` 可空，至少与 `tags` / `item_type` / `kind` 之一配合使用，持久化 localStorage `vault-editor:searchMode`。
- 可选 tag 过滤：候选来自 `GET /api/vault/{lang}/tags`（底层 MCP `list_tags`）。用 Badge 风格 `<Button variant="outline">` 多选切换；≥1 tag 选中时显示 `tags_op`（and/or）toggle。
- tag 列表末尾有一个刷新按钮（`RefreshCw` 图标），点击手动重拉 `list_tags` 以同步笔记 tag 增删。tag 区块在 `selectedLang` 存在时常驻显示（无 tag 时显示「暂无 tag」提示）。
- 触发 `POST /api/vault/{lang}/search`（底层 MCP `search`）。
- 结果列表展示 `title` / `item_type` / `snippet` / `file_path`，点击 → **不切 tab**，仅调用 `handleFileSelect` 加载文件到右侧编辑区；命中列表中与当前 `currentPath` 匹配的条目高亮 `bg-muted`，支持连续点击多个结果切换浏览。命中块 `chunk.char_offset` 滚动到对应段为后续迭代，MVP 仅跳到文件。

### 编辑区（Milkdown）

- 组件库：Milkdown（`@milkdown/kit` + `@milkdown/react`）。原生支持 source / WYSIWYG 双模式切换。
- Source 模式采用 CodeMirror 6（`@codemirror/lang-markdown` + `@codemirror/language-data`），markdown 语法着色，围栏代码块按 yaml/json/bash 等语言自动高亮；关闭行号，开启自动换行。
- frontmatter：MVP 下 Source 模式原样保留；WYSIWYG 模式剥离 frontmatter 仅渲染 body，编辑时保留原 frontmatter 拼回保存。frontmatter 表单化作为后续迭代。
- 自动保存：MVP 不做；仅手动「保存」按钮。
- 未保存改动离开页面 / 切文件 → `beforeunload` + React 内 confirm。

#### 链接点击行为（WYSIWYG 模式）

WYSIWYG 模式中，单击 markdown 渲染出的 `<a>` 链接时：

1. **`/editor?lang=...&path=...` 同源内部链接** → 在当前编辑区加载（未保存改动先 confirm；lang 不同时自动切换语言 + 重拉树），不开新 tab。
2. **vault 路径**（不以 `://` 开头，如 `items/vocab/god.md`、`./sibling.md`、`/items/root.md`）→ 解析为 vault 内的绝对路径：
   - 以 `/` 开头 → 从 vault 根算（去除前导 `/`）；
   - 否则相对当前文件所在目录解析（支持 `./`、`../`）；
   - 无 `.` 后缀 → 自动补 `.md`；
   - 规范化路径后，在当前编辑区加载（同 `/editor` 链接流程：未保存 confirm、跨 lang 切换）。
3. **外链**（`http://`、`https://` 等含协议的 URL）→ `window.open(href, '_blank', 'noopener,noreferrer')` 新 tab 打开。

Source 模式（CodeMirror）不渲染链接，不做处理。

实现：`MilkdownEditor.tsx` 在 WYSIWYG 容器 `<div>` 上挂 `onClick` 事件代理，检测 `[data-milkdown-root] a[href]` → `preventDefault()`（阻止 ProseMirror 放置光标）→ 调用 `EditorApp` 传入的 `onLinkClick` prop；`EditorApp.handleEditorLinkClick` 完成路径解析与文件加载。

### 从 chatbot 跳入

chatbot 的 markdown 消息里可包含指向 editor 的链接，由 `react-markdown` 渲染为 `<a>`：

```markdown
详见 [god 词条](/editor?lang=en&path=items/vocab/god.md)
```

#### 链接点击行为

Web Chatbot 不直接依赖 Vault Editor。`ChatWindow` 接受可选的 `linkListener?: (url: string) => boolean` prop：

- **独立 chatbot**（无 listener）：所有链接默认在新 Tab 打开（`<a target="_blank" rel="noopener noreferrer">`）。
- **嵌入到 editor**（`<ChatWindow embedded linkListener={handleChatLinkClick} />`）：点击链接时先调用 listener；返回 `true` 表示消费事件（chatbot 不再处理），返回 `false` 回退默认（新 Tab）。

editor 的 `handleChatLinkClick(url)` 逻辑：
1. 解析 URL；若 `origin !== location.origin`、`pathname !== '/editor'`、或无 `path` 查询参数 → 返回 `false`（回退新 Tab）。
2. 取 `lang` / `path` 参数；若 `lang` 不在已知 langs 列表 → 返回 `false`。
3. 若编辑器有未保存改动 → `confirm()`；用户取消 → 返回 `true`（消费事件，不导航）。
4. 异步加载文件：若 `lang !== selectedLang` 先切 lang + 重拉 tree，再 `read(lang, path)` 加载到编辑区；返回 `true`。

#### editor 启动参数

editor app 启动时读 `location.search`：
- `lang` → 预选 lang selector
- `path` → 自动打开文件
- `q` → 进入 Search tab + 预填搜索框 + 自动跑一次 `search`
- `tag` → 预填 tag 过滤（可多个 `&tag=vocab&tag=grammar`）

`MarkdownRenderer` 组件统一给 `<a>` 加 `target="_blank" rel="noopener noreferrer"`，点击时若存在 `linkListener` 则先调用。

**URL 同步**：editor 在选中/切换文件时通过 `history.replaceState` 把当前 `lang`、`path` 同步到地址栏，格式为 `/editor?lang=en&path=items/vocab/god.md`。`q`/`tag` 等搜索参数不留在 URL 中。用户可复制地址栏 URL 作为该文件的直接入口。刷新页面后按 URL 参数恢复 lang 与打开的文件。

反向链接（editor → chatbot）：chatbot 的 session id 与消息历史持久化在 `sessionStorage`（见 [web-chatbot.md](web-chatbot.md)「会话状态持久化」）。同一浏览器 Tab 内 editor ↔ chatbot 相互跳转会复用同一 session，Agent 上下文与消息历史连续；新开 Tab 则新建 session（`sessionStorage` 按 Tab 隔离）。

### 编辑器上下文注入

chatbot 侧栏发送消息时，通过 `resourceContextProvider` 回调把编辑器当前上下文注入 envelope 的 `chat_context.resource_contexts`：

- **当前打开的文件** → `{kind: 'vault_file', file_path}`，取值来自 `EditorApp` 的 `currentPath` state。
- **编辑器选区文本**（Source 模式） → `{kind: 'selected_text', text, start_line, start_column, paragraph_text}`：
  - `text`：选中的文本内容
  - `start_line` / `start_column`：选区起始的行号和列号（从 CodeMirror `view.state.selection` 取得）
  - `paragraph_text`：选区所在行的行文本（`view.state.doc.lineAt(sel.from).text`）
- **编辑器选区文本**（WYSIWYG 模式） → 同上，但 `start_line` / `start_column` 为 `null`（ProseMirror 下不可得）；`paragraph_text` 取选区所在最近 block node 的 textContent。
- 无选区或未打开文件时对应项缺省，无缺省内容时 `resource_contexts` 为空数组。

实现：
- `EditorApp` 通过 `useRef` 创建一个 `editorSelectionRef`，传递给 `MilkdownEditor`。
- `MilkdownEditor` 根据模式（source / wysiwyg）转发给 `SourceEditor` 或 `WysiwygEditor`，组件在挂载时用 `selectionRef.current = () => { ... }` 注册一个懒取选区文本的函数。
- `EditorApp.getEditorResourceContext()` 读取 `currentPath` + `editorSelectionRef.current()` 构造 `ResourceContext[]`。
- `ChatWindow` 通过 `resourceContextProvider` prop 接收该函数，发送消息时调用并拼入 `buildEnvelope`。
- **选区视觉持久化**：
  - Source 模式：启用 CM6 的 `drawSelection()` 扩展（`@codemirror/view`），由 CM6 自行渲染选区 DOM 元素而非依赖浏览器原生 `::selection`。编辑器失焦后选区高亮依然可见（颜色略淡，见 `SourceEditor.tsx` 的 `.cm-selectionBackground` 主题）。
  - WYSIWYG 模式：通过 ProseMirror 插件 `ghostSelectionPlugin.ts`，在失焦时用 `Decoration.inline` 绘制 `.pm-ghost-selection` 背景，失焦后选区高亮保持可见（颜色同 Source 模式失焦色 `oklch(0.9 0.02 260)`）。

## 移动端适配

以 Tailwind 默认 `md` 断点（768px）为界：
- `>= md`：桌面三栏 flex 布局，行为不变。
- `< md`（iPhone / 窄手机）：移动端抽屉模式。

### 断点
`md` (768px)。iPad 竖屏(768px) 及宽屏手机走桌面布局。所有响应式类使用 `md:` 前缀。

### 按钮文字标签自适应隐藏
所有「图标 + 文字」按钮的文字用 `<span className="hidden md:inline">` 包裹，图标常驻。`< md` 只显示图标，`>= md` 显示完整文字。涉及：

| 位置 | 按钮 | 文件:行 |
|------|------|---------|
| Header | 呼叫小记 | `EditorApp.tsx:430` |
| Header | 转到小记 | `EditorApp.tsx:438` |
| Editor sub-header | 标题（🐹 小记笔记编辑器） | `EditorApp.tsx:415-416` |
| Editor sub-header | 源码 | `EditorApp.tsx:564` |
| Editor sub-header | 直观 | `EditorApp.tsx:574` |
| Editor sub-header | 保存 | `EditorApp.tsx:586` |
| Editor sub-header | 刷新（纯图标） | `EditorApp.tsx:553` |
| Left pane tab bar | Files | `EditorApp.tsx:476` |
| Left pane tab bar | Search | `EditorApp.tsx:490` |

ChatInput 的 `发送` 按钮保留文字（右侧抽屉内空间足够）。

### 左栏 toggle（新增）
左栏（文件树/搜索）原先一直常驻，移动端新增 toggle：
- `leftOpen` state，移动端初始 `false`。
- Header 最左加汉堡按钮（`Menu` 图标，`md:hidden`），点击 toggle `leftOpen`。
- 桌面端 `leftOpen` 无效（左栏始终 flex 显示）。

### 抽屉模式（< md）
两个 `<aside>` 改为 fixed overlay + 滑入：

- **左 aside**：`fixed inset-y-0 left-0 z-40 w-[85vw] max-w-sm` + `translate-x-0`/`-translate-x-full` 控制开合。桌面端恢复 `flex shrink-0` + 百分比宽度。
- **右 aside（chatbot）**：同理，右侧滑入（`fixed inset-y-0 right-0`）。桌面端继续 flex + `hidden` class 切换。`chatMounted`/`chatOpen` 机制不变——SSE session 在关闭时不卸载。
- **Backdrop**：任一抽屉打开时渲染 `<div className="fixed inset-0 z-30 bg-black/40" onClick={closeAll} />`。
- **互斥**：移动端打开一个抽屉时自动关闭另一个；backdrop 点击关闭所有抽屉。

### Resize 手柄隐藏
左右 resize 手柄加 `hidden md:block`，移动端不可见不可拖。

### 宽度持久化
桌面端 `leftPanePct`/`chatPanePct` 逻辑不变，移动端不读不写百分比。用 `useMediaQuery('(min-width: 768px)')` 得 `isDesktop`，条件传 inline width（仅桌面传百分比）。

### 新增 hook
`web/src/editor/hooks/useMediaQuery.ts`：`matchMedia` + useEffect listener。

### 已知限制 / 后续迭代
- **FileTree 右键菜单**（新建文件/目录、重命名、删除）触屏不可用。需后续增加 long-press 或显式「⋯」按钮操作菜单。
- **`beforeunload` dirty guard** 移动端浏览器行为弱化，不在本次范围。

## 前端技术选型

沿用 [Standalone Web Chatbot §前端技术选型](/docs/impl-spec/web-chatbot.md)：Vite + React + TailwindCSS + shadcn/ui + react-markdown。

新增编辑器专用依赖：
- `@milkdown/kit`
- `@milkdown/react`
- `@milkdown/crepe`（可选，开箱即用 preset；若用则可省去部分手配）

新增 shadcn 组件（`npx shadcn@latest add context-menu`，基于 Base UI `@base-ui/react/context-menu`，与 button/input 同栈）。

### Favicon

与 chatbot 共用同一 `web/public/favicon.png`（源图 `docs/arts/chrome-icon.png`），Vite `public/` 约定自动部署。两个 html 入口均已添加 `<link rel="icon" type="image/png" href="/favicon.png" />`；后端 catch-all 路由可直接服务 `GET /favicon.png`。

### Vite 多入口

`web/vite.config.ts` 的 `build.rollupOptions.input` 改为多入口：

```js
input: {
  main:   'index.html',
  editor: 'editor.html',
}
```

- `web/index.html` → chatbot（不动）
- `web/editor.html` → editor，加载 `web/src/editor/main.tsx`

两个应用共享 `web/src/components/ui/`（shadcn）、`tailwind`、`react-markdown`、`types`；各自独立的入口、状态、路由、构建产物。

### 组件结构（editor 侧）

```
web/src/editor/
  main.tsx
  components/
    EditorApp.tsx          # 三栏布局 + 状态总管 + 左栏 Tab 切换 + 可调宽
    FileTree.tsx          # 文件树 + 新建/重命名/删除
    SearchBar.tsx         # 搜索 + tag 过滤（Tab 切换，点击结果不切 tab）
    MilkdownEditor.tsx    # 双模式切换 + frontmatter 代码块
  services/
    vaultApi.ts           # fetch 封装 /api/vault/...
  types/
    vault.ts
```

## 后端

新增 `src/everlingo/gateway/vault_editor_api.py`，挂载到 `web_acceptor.py` 的同一 FastAPI `app`（即 `localhost:8000`）。

### MCP Client

参考 [mem_writer_mcp_client.py](/src/everlingo/mem/agents/mem_writer_mcp_client.py) 模式新建一个轻量 MCP client：
- 读 `workspace.indexer_mcp_url_path()` 获取 URL。
- FastMCP Client 连 streamable-http。
- **进程级单例 + 懒连接 + 断线重连**。
- 单用户本地场景下，单一持久 MCP stream 即可满足。每次 REST 请求按需 `session.configure(lang)` 切换会话 lang——重配成本可忽略，避免多 stream 管理复杂度。
- 后续若要支持多 tab 并发不同 lang，可升级为 per-tab stream。

### REST 端点（前缀 `/api/vault`）

所有端点路径中的 `{lang}` 必须是 workspace 已存在的 lang（底层 MCP `session.configure` 校验）。

| Method & Path | 底层 MCP 工具 | 备注 |
|---|---|---|
| `GET  /api/vault/langs` | `list_vaults` | 不需要 configure |
| `GET  /api/vault/{lang}/tree?path=` | `configure` + `tree` | 过滤 `tmp/`（默认）与 dotfile/dotdir（name 以 `.` 开头，硬过滤无 toggle）；后端遍历 entries 读 frontmatter 前 4KB 注入可选 `title`（文件取自身 frontmatter，目录取 `index.md` 的 frontmatter） |
| `GET  /api/vault/{lang}/read?path=` | `configure` + `read` | |
| `POST /api/vault/{lang}/write` `{path, content}` | `configure` + `write` | |
| `POST /api/vault/{lang}/append` `{path, content}` | `configure` + `append` | |
| `POST /api/vault/{lang}/mkdir` `{path}` | `configure` + `mkdir` | |
| `POST /api/vault/{lang}/delete` `{path}` | `configure` + `delete` | |
| `POST /api/vault/{lang}/rename` `{from, to}` | `configure` + `read` + `write` to + `delete` old | MCP 无 rename 原语，复合实现；对大文件有窗口期，MVP 接受 |
| `POST /api/vault/{lang}/search` `{q, mode, tags, tags_op, limit}` | `configure` + `search` | `lang` 不传，用会话 lang |
| `GET  /api/vault/{lang}/tags` | `configure` + `list_tags` | |

**错误归一**：MCP 工具返回 `isError=true` 时，后端把 `content[0].text` 包成 HTTP 4xx/5xx + `{ "detail": "<text>" }`。常见错误：
- `session not configured: call session.configure first` → 500（后端 bug，不应让客户端看到）
- `path escape` / 路径越界 → 400
- 文件不存在（`read`/`delete`） → 404
- lang 不存在 → 404

### web_acceptor catch-all 调整

`web_acceptor.py:113-128` 的 catch-all 改为：
- `/editor` 及 `/editor/{path}` → 返回 `web/dist/editor.html`（前端 SPA 路由 fallback）
- 其余 fallback `index.html`

实现时注意顺序：`/editor` 路由需在 catch-all `/{path:path}` 之前注册。

### LAN 安全

默认 `listener.interface=localhost` 仅本机访问。如需 LAN 访问，在 `everlingo.yaml` 中配置 `plugins.channels.channel_web.listener.interface=0.0.0.0`。后续如需进一步收敛，最少在编辑器写 API 校验 `request.client.host` 为 loopback。

## 与 chatbot 的关系

- 共用 HTTP server、origin、Vite 工程、shadcn/ui 组件库。
- 不共享 React 状态：editor 与 chatbot 各为独立组件实例、独立 React 状态。
- chatbot markdown 链接到 editor 见上「从 chatbot 跳入」。
- editor → chatbot 反向链接：右侧 chatbot 侧栏（「呼叫小记」按钮 toggle）内嵌 `ChatWindow` 组件，首次打开时建 session，关闭仅隐藏不卸载，session 持续保持。

## 实现顺序（建议分 PR）

1. **chatbot → editor 链接**：`MarkdownRenderer` 链接 `target` 策略 + editor 启动参数解析。

## 不在本 spec 范围

- frontmatter 表单化编辑（后续迭代）。
- 命中块 `chunk.char_offset` 滚动到对应段（后续迭代）。
- 多 tab 并发不同 lang 的 per-tab MCP stream。
- 自动保存 / 协作编辑 / 版本历史。
- 图片上传与预览（vault 当前 spec 未涉及图片）。

## 手工验证
http://localhost:8000/editor 
