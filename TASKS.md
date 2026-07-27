# Current Sprint

## 进行中的任务

## 完成的任务
格式：完成日期与时间(北京时间) | 任务描述 。 示例：" - 2026-06-20 19:28 | 生成主入口代码"
- 2026-07-26 22:50 | PWA 可安装到主屏（无离线）—— manifest / icon / HTML meta / 后端静态文件路由
- 2026-07-27 11:54 | Chrome Extension SSE 自动重连——修复 session 过期无限 404 循环，`connectSSE` 增加 `ConnStatus` / `onStatus` / `retryNow` / 指数退避，`ChatWindow` 加 amber 提示条 + `handleRebuild`
- 2026-07-27 13:20 | 修复 gateway 不启动（entrypoint.sh TOCTOU 读到上轮残留 mcp.url，host_port 缓存后永不更新）+ MCP 端口从随机改为默认 8100 + 冲突回退。涉及文件：entrypoint.sh（方案 C：启动前 rm -f 残留 + TCP 循环内重读 port）；server.py _run_indexer（方案 D：启动时 unlink 残留 mcp.url）；mcp_server.py（DEFAULT_MCP_PORT=8100 + pick_free_port(preferred=) 回退逻辑 + 2 个单测）；vault-mcp-spec.md / container-spec.md 同步文档
- 2026-07-27 16:05 | Vault Editor sub-header 新增刷新按钮（纯图标、`RefreshCw`），位于「源码」按钮左侧，重新从服务器加载当前文件内容。涉及文件：EditorApp.tsx（import / reloadFile callback / 按钮 UI）；vault-editor.md（表格追加一行 + 纯图标说明）
- 2026-07-27 16:30 | 修复刷新按钮和同文件再点击后编辑器内容不更新的 bug——引入 `reloadNonce` state，在 `handleFileSelect` / `reloadFile` 成功后自增，注入 `MilkdownEditor` key 驱动 remount。涉及文件：EditorApp.tsx（纯图标、`RefreshCw`），位于「源码」按钮左侧，重新从服务器加载当前文件内容。涉及文件：EditorApp.tsx（import / reloadFile callback / 按钮 UI）；vault-editor.md（表格追加一行 + 纯图标说明）
- 2026-07-27 17:00 | 拆分 `source.kind`：Chrome Extension 由 `web` 改为 `chrome_ext`，与 Standalone Web Chatbot 的 `web` 区分。涉及文件：envelope.py（新增 SourceChromeExt、收窄 SourceWeb.surface 为 fullscreen）；test_envelope.py（SourceChromeExt 测试 + surface 校验更新）；envelope_spec.md（kind 表格 + chrome_ext 节 + 示例）；extension types/envelope.ts + test（kind/类型/buildEnvelope）；文档同步（chrome-extension-spec.md / chrome-extension-impl-spec.md / envelope-impl-spec.md / web-session-acceptor.md）
