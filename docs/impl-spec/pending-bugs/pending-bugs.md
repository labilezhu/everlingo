实现了 docs/impl-spec/vault-editor.md 中 “## 实现顺序（建议分 PR）” 的 “2. 接入 Milkdown” 后。
1. 问题1 ： 在 浏览器 http://localhost:8000/editor 前端在 WYSIWYG 模式下。点击文件，editor 主编辑界面没有变化。只有在 从 Source 模切换到 WYSIWYG 模式 时，才显示 Milkdown 可视编辑区。
2. 问题2 : WYSIWYG 成功加载 markdown 文件后， frontmatter 没有分行。 这样，我建议现在直接不要在 WYSIWYG 模式下， 显示 frontmatter 好了

---

实现了 docs/impl-spec/vault-editor.md 中 “## 实现顺序（建议分 PR）” 的 “2. 接入 Milkdown” 后。
能不能为编辑器的 source 模式做个 markdown 语法 hightlight


---

实现了 docs/impl-spec/vault-editor.md 中 “## 实现顺序（建议分 PR）” 的 “2. **Vite 多入口改造 + editor 骨架**” 后。
在 浏览器 http://localhost:8000/editor 中点击目录 /items/grammar 时，后端报以下错。
我看了一个，去 read 一个 directory 这个行为的确有问题。

```log
(.venv) labile@labile-hp ➜ everlingo $ uv run python -m everlingo mem indexer start
indexer 启动（前台）：socket=/home/labile/.everlingo/workspaces/default/indexer.sock log=/home/labile/.everlingo/workspaces/default/logs/indexer.log
[07/21/26 21:25:24] Error calling tool 'read'                                
                    ╭────────── Traceback (most recent call last) ──────────╮
                    │ /home/labile/everlingo/.venv/lib/python3.12/site-pack │
                    │ ages/fastmcp/server/server.py:1312 in call_tool       │
                    │                                                       │
                    │ /home/labile/everlingo/.venv/lib/python3.12/site-pack │
                    │ ages/fastmcp/tools/base.py:421 in _run                │
                    │                                                       │
                    │                ... 4 frames hidden ...                │
                    │                                                       │
                    │ /home/labile/everlingo/src/everlingo/mem/vault/mcp_se │
                    │ rver/mcp_server.py:237 in wrapper                     │
                    │                                                       │
                    │   234 │   │   │   params = _format_tool_params(func,  │
                    │   235 │   │   │   logger.debug("tool_name: %s , param │
                    │   236 │   │   │   try:                                │
                    │ ❱ 237 │   │   │   │   result = await func(*args, **kw │
                    │   238 │   │   │   except BaseException as e:          │
                    │   239 │   │   │   │   logger.debug(                   │
                    │   240 │   │   │   │   │   "tool_name: %s , parameters │
                    │                                                       │
                    │ /home/labile/everlingo/src/everlingo/mem/vault/mcp_se │
                    │ rver/mcp_server.py:523 in read_tool                   │
                    │                                                       │
                    │   520 │   │   except PathEscapeError as e:            │
                    │   521 │   │   │   raise RuntimeError(str(e)) from e   │
                    │   522 │   │   if not abs_path.is_file():              │
                    │ ❱ 523 │   │   │   raise RuntimeError(f"file not found │
                    │   524 │   │   content = abs_path.read_text(encoding=" │
                    │   525 │   │   size = abs_path.stat().st_size          │
                    │   526 │   │   return {"path": path, "content": conten │
                    ╰───────────────────────────────────────────────────────╯
                    RuntimeError: file not found: 'items/grammar'    
```

---

实现完 extension/chrome-extension-impl-spec.md 后，手工在浏览器上测试，发现问题：
浏览器中，side panel 可以显示，但提示： 连接断开，请刷新页面重试
服务端 `.venv/bin/python -m everlingo.gateway.gateway --channel_web` 有错误日志：
```log
INFO:     Started server process [3606065]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     127.0.0.1:60518 - "POST /api/session HTTP/1.1" 200 OK
INFO:     127.0.0.1:60518 - "OPTIONS /api/session/undefined/message HTTP/1.1" 405 Method Not Allowed
INFO:     127.0.0.1:60530 - "GET /api/session/undefined/events HTTP/1.1" 404 Not Found
```

补充以下 Chrome Extension DevTools Console 提示：
```log
sidecar.html:1 Access to fetch at 'http://localhost:8000/api/session/undefined/message' from origin 'chrome-extension://fahmknjmbjccegjancflflfceobbcmld' has been blocked by CORS policy: Response to preflight request doesn't pass access control check: No 'Access-Control-Allow-Origin' header is present on the requested resource.
localhost:8000/api/session/undefined/message:1  Failed to load resource: net::ERR_FAILED
sidecar.html:1 Access to resource at 'http://localhost:8000/api/session/undefined/events' from origin 'chrome-extension://fahmknjmbjccegjancflflfceobbcmld' has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present on the requested resource.
localhost:8000/api/session/undefined/events:1  Failed to load resource: net::ERR_FAILED
```

---
