# Vault Editor

Web 前端给用户一个可视化编辑 [Memory Vault](/src/everlingo/mem/vault/templates/default/spec/vault_spec.md) 中 markdown 文件的编辑器。支持 源码 / WYSIWYG 双模式切换、文件树浏览、搜索。

编辑器入口 URL：`http://localhost:8000/editor`。

与 [Standalone Web Chatbot](/docs/impl-spec/standalone-web-chatbot.md) 共用同一 HTTP server（[Web Session Acceptor](/docs/impl-spec/web-session-acceptor.md)），同一 origin，不同前端入口。前端代码位于同一 Vite 工程 `/web`，多入口构建。

## 通用界面设计风格
沿用 [Standalone Web Chatbot §通用界面设计风格](/docs/impl-spec/standalone-web-chatbot.md)：主可视区域宽度跟随窗口动态调整，左右边缘适当留白。

## 编辑器界面设计

三栏布局：

```
┌─────────────────────────────────────────────────────────────┐
│ Header：lang selector  |  模式切换 (源码/WYSIWYG)  |  保存    │
├──────────┬──────────────────────────────────────────────────┤
│          │                                                   │
│  文件树  │              编辑区（Milkdown）                   │
│  / 搜索  │                                                   │
│ (可调宽) │                                                   │
└──────────┴──────────────────────────────────────────────────┘
```

左栏宽度可调。两栏之间有一个 4px 拖拽手柄，hover 时变色并显示 `col-resize` 光标。拖拽通过 Pointer Events 实现，宽度按百分比记录到 localStorage（key `vault-editor:leftPanePct`，默认 22%，范围 15%-50%）。刷新/重开页面后恢复。

### Header

- **lang selector**：单选下拉，候选项来自 `GET /api/vault/langs`（底层 MCP `list_vaults`）。切换 lang 重新拉取文件树。
- **模式切换**：source / WYSIWYG 两态 toggle，组件内持久化。
- **保存**：将当前编辑器内容 `POST /api/vault/{lang}/write`。未改动时禁用；改动未保存时按钮高亮 + 关闭/切文件前 confirm。

### 文件树（FileTree）

- 数据源：`GET /api/vault/{lang}/tree`（底层 MCP `tree`）。
- 树形展开/折叠，点击文件 → 加载到编辑区。
- 子目录懒加载：首次展开 children 为空的目录时，按需调用 `tree(path=<dir>, depth=2)` 拉取该目录的子项并合并到树状态。已加载的目录再次折叠/展开不重复请求。
- 右键菜单 / 顶部按钮组：
  - 新建文件（输入 path，自动 `.md` 后缀）
  - 新建目录
  - 重命名（MVP 走 read+write+delete 复合，见下「后端 REST 端点」）
  - 删除
- **`tmp/` 目录默认隐藏**；顶部 toggle「显示隐藏目录」可切换。`tmp/` 不入索引（见 [vault-mcp-spec.md](/docs/impl-spec/vault-mcp/vault-mcp-spec.md)「`spec/` 目录不入索引」段的 `is_excluded_vault_file` 描述）。
- `spec/` 目录允许编辑（与其它目录同权）。

### 搜索（SearchBar）

左栏采用 Files / Search **Tab 切换**（互斥；`hidden` CSS 保留各自状态以维持滚动位置和输入内容）。URL 带 `q` 参数时初始进入 Search tab；否则优先读 localStorage（key `vault-editor:leftTab`），缺省 Files。

- 搜索框（`<Input>`）+ Enter / 按钮触发。
- 模式选择：hybrid / exact / semantic 三态 `<Button>` toggle（默认 hybrid），持久化 localStorage `vault-editor:searchMode`。
- 可选 tag 过滤：候选来自 `GET /api/vault/{lang}/tags`（底层 MCP `list_tags`）。用 Badge 风格 `<Button variant="outline">` 多选切换；≥1 tag 选中时显示 `tags_op`（and/or）toggle。
- 触发 `POST /api/vault/{lang}/search`（底层 MCP `search`）。
- 结果列表展示 `title` / `item_type` / `snippet` / `file_path`，点击 → **不切 tab**，仅调用 `handleFileSelect` 加载文件到右侧编辑区；命中列表中与当前 `currentPath` 匹配的条目高亮 `bg-muted`，支持连续点击多个结果切换浏览。命中块 `chunk.char_offset` 滚动到对应段为后续迭代，MVP 仅跳到文件。

### 编辑区（Milkdown）

- 组件库：Milkdown（`@milkdown/kit` + `@milkdown/react`）。原生支持 source / WYSIWYG 双模式切换。
- Source 模式采用 CodeMirror 6（`@codemirror/lang-markdown` + `@codemirror/language-data`），markdown 语法着色，围栏代码块按 yaml/json/bash 等语言自动高亮；关闭行号，开启自动换行。
- frontmatter：MVP 下 Source 模式原样保留；WYSIWYG 模式剥离 frontmatter 仅渲染 body，编辑时保留原 frontmatter 拼回保存。frontmatter 表单化作为后续迭代。
- 自动保存：MVP 不做；仅手动「保存」按钮。
- 未保存改动离开页面 / 切文件 → `beforeunload` + React 内 confirm。

### 从 chatbot 跳入

chatbot 的 markdown 消息里可包含指向 editor 的链接，由 `react-markdown` 渲染为 `<a>`：

```markdown
详见 [god 词条](/editor?lang=en&path=items/vocab/god.md)
```

editor app 启动时读 `location.search`：
- `lang` → 预选 lang selector
- `path` → 自动打开文件
- `q` → 进入 Search tab + 预填搜索框 + 自动跑一次 `search`
- `tag` → 预填 tag 过滤（可多个 `&tag=vocab&tag=grammar`）

`MarkdownRenderer` 组件需统一链接 `target` 策略：站内 `/editor...` 同窗跳转，外链新开 tab。

**URL 同步**：editor 在选中/切换文件时通过 `history.replaceState` 把当前 `lang`、`path` 同步到地址栏，格式为 `/editor?lang=en&path=items/vocab/god.md`。`q`/`tag` 等搜索参数不留在 URL 中。用户可复制地址栏 URL 作为该文件的直接入口。刷新页面后按 URL 参数恢复 lang 与打开的文件。

反向链接（editor → chatbot）不在本 spec 范围：chatbot 使用 session id，跨页跳转会建新 session，需独立设计。

## 前端技术选型

沿用 [Standalone Web Chatbot §前端技术选型](/docs/impl-spec/standalone-web-chatbot.md)：Vite + React + TailwindCSS + shadcn/ui + react-markdown。

新增编辑器专用依赖：
- `@milkdown/kit`
- `@milkdown/react`
- `@milkdown/crepe`（可选，开箱即用 preset；若用则可省去部分手配）

新增 shadcn 组件（`npx shadcn@latest add context-menu`，基于 Base UI `@base-ui/react/context-menu`，与 button/input 同栈）。

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
| `GET  /api/vault/{lang}/tree?path=` | `configure` + `tree` | 过滤 `tmp/`（默认） |
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

暂不处理（保持 `0.0.0.0` 绑定与现状一致）。后续如需收敛，最少在编辑器写 API 校验 `request.client.host` 为 loopback。

## 与 chatbot 的关系

- 共用 HTTP server、origin、Vite 工程、shadcn/ui 组件库。
- 不共享 React 状态、不共享 session：editor 无 session 概念，每次请求独立。
- chatbot markdown 链接到 editor 见上「从 chatbot 跳入」。

## 实现顺序（建议分 PR）

1. **后端**：`vault_editor_api.py` + MCP client + 端到端打通 `langs`/`tree`/`read`/`write`，单测覆盖翻译层。
2. **Vite 多入口改造 + editor 骨架**：`editor.html` + `EditorApp` + `FileTree` + `MilkdownEditor`（先用 textarea），read/write 端到端。
3. **接入 Milkdown** + 双模式切换。
4. **搜索栏** + tag 过滤 + 左栏可调宽。SearchBar 新建组件（左栏 Search tab，结果列表点击不切 tab，仅更新 editor）；EditorApp 左栏改 Files/Search Tab 切换 + 可拖拽调整宽度（百分比持久化 localStorage）；URL `q`/`tag` 参数解析与预填。
5. **新建/重命名/删除文件和目录** 在 file explorer 的 file/directory 上右键或长按（触屏，由 Base UI ContextMenuTrigger 原生支持）可以跳出 context menu。
   - 实现依赖：`shadcn@latest add context-menu`（Base UI 后端，匹配现有 base-nova 风格）。
   - 菜单项按 entry 类型区分：目录有"新建文件/新建目录/重命名/删除"；文件有"重命名/删除"。
   - 删除前 `window.confirm` 二次确认。
   - 名称输入：行内 `<Input>`，回车确认、Esc 取消、失焦空值取消。新建文件自动补 `.md` 后缀。
   - 新建文件通过 `write(lang, path, '')` 创建空文件（复用现有端点）。
   - 操作成功后 `tree(selectedLang)` 整树重拉刷新（懒加载状态重置，简单可靠）。
   - rename 命中 `currentPath` 时更新路径；delete 命中 `currentPath` 或其祖先时清空编辑区。
6. **chatbot → editor 链接**：`MarkdownRenderer` 链接 `target` 策略 + editor 启动参数解析。

## 不在本 spec 范围

- frontmatter 表单化编辑（后续迭代）。
- 命中块 `chunk.char_offset` 滚动到对应段（后续迭代）。
- editor → chatbot 反向链接（需独立 session 设计）。
- 多 tab 并发不同 lang 的 per-tab MCP stream。
- 自动保存 / 协作编辑 / 版本历史。
- 图片上传与预览（vault 当前 spec 未涉及图片）。

## 手工验证
http://localhost:8000/editor 
