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
│  + 搜索  │                                                   │
│          │                                                   │
└──────────┴──────────────────────────────────────────────────┘
```

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

- 搜索框 + 模式选择（hybrid / exact / semantic，默认 hybrid）+ 可选 tag 过滤（tag 候选来自 `GET /api/vault/{lang}/tags`，底层 MCP `list_tags`）。
- 触发 `POST /api/vault/{lang}/search`（底层 MCP `search`）。
- 结果列表展示 `title` / `item_type` / `snippet` / `file_path`，点击 → 在文件树中定位并加载该文件。命中块 `chunk.char_offset` 滚动到对应段为后续迭代，MVP 仅跳到文件。

### 编辑区（Milkdown）

- 组件库：Milkdown（`@milkdown/kit` + `@milkdown/react`）。原生支持 source / WYSIWYG 双模式切换。
- frontmatter：MVP 在两种模式下均作为代码块原样呈现，**不**解析为表单。frontmatter 表单化作为后续迭代。
- 自动保存：MVP 不做；仅手动「保存」按钮。
- 未保存改动离开页面 / 切文件 → `beforeunload` + React 内 confirm。

### 从 chatbot 跳入

chatbot 的 markdown 消息里可包含指向 editor 的链接，由 `react-markdown` 渲染为 `<a>`：

```markdown
详见 [god 词条](/editor?lang=en&path=items/vocab/god--01KWDVQ6GMWPNTMY4BSNSCDBE.md)
```

editor app 启动时读 `location.search`：
- `lang` → 预选 lang selector
- `path` → 自动打开文件
- `q` → 进入时跑一次 `search` 并高亮命中块（后续迭代；MVP 仅预填搜索框）
- `tag` → 预填 tag 过滤

`MarkdownRenderer` 组件需统一链接 `target` 策略：站内 `/editor...` 同窗跳转，外链新开 tab。

反向链接（editor → chatbot）不在本 spec 范围：chatbot 使用 session id，跨页跳转会建新 session，需独立设计。

## 前端技术选型

沿用 [Standalone Web Chatbot §前端技术选型](/docs/impl-spec/standalone-web-chatbot.md)：Vite + React + TailwindCSS + shadcn/ui + react-markdown。

新增编辑器专用依赖：
- `@milkdown/kit`
- `@milkdown/react`
- `@milkdown/crepe`（可选，开箱即用 preset；若用则可省去部分手配）

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
    EditorApp.tsx          # 三栏布局 + 状态总管
    FileTree.tsx          # 文件树 + 新建/重命名/删除
    SearchBar.tsx         # 搜索 + tag 过滤
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
4. **搜索栏** + tag 过滤。
5. **新建/重命名/删除** + `tmp/` 隐藏 toggle。
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
