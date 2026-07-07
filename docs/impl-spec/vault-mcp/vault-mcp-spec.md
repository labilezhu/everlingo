# Vault MCP Spec

基于 [MCP 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25) 规范， 实现一个 支持 [Streamable HTTP Transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports#streamable-http) 的 MCP Server 。

技术选型：使用 FastMCP 。

## 部署形态

本 MCP Server **内嵌于 indexer 进程**（方案 C：合并部署），与 indexer 的 HTTP/UDS REST API 共进程，监听不同端口：

- indexer 进程同时承载两个对外接口：
  1. HTTP over unix socket REST API（`$workspace/indexer.sock`，FastAPI/uvicorn）—— 现有 `/{lang}/search|index|delete|rebuild|embed`、`/status`，给 gateway / CLI 等外部客户端用。契约见 [search-api-spec.md](/docs/impl-spec/search/search-api-spec.md)。
   2. MCP 2025-11-25 Streamable HTTP Server —— 给 LLM agent / MCP 客户端用，暴露 fs 工具 + `search` 工具 + `session.configure` 工具 + `gen_id` Utility 工具。
- indexer 启动时把 MCP Streamable HTTP URL 写入 `$workspace/indexer.mcp.url` 文件，MCP 客户端据此连接。
- 进程拓扑见 [memory-vault-search-spec.md](/docs/impl-spec/search/memory-vault-search-spec.md)「进程拓扑」。

工具定义见 [vault-mcp-spec-tools.yaml](vault-mcp-spec-tools.yaml)。


## 会话 lang 机制

MCP Server 不在启动时绑定单一 lang；而是通过 `session.configure` 工具在会话内设定会话默认 lang（及其它会话级默认值）。设计要点：

- **必须先 configure**：agent 调用任何 fs 工具（ls/read/write/grep/find/stat/mkdir/delete/tree）或 `search` 工具之前，必须先调用 `session.configure` 设定会话 lang；否则上述工具返回错误 `session not configured: call session.configure first`。无隐式回退（不自动取 workspace 唯一 lang、不自动取 indexer 启动默认 lang）——强制显式，促使 agent 建立正确习惯。
- **可重调切换**：会话内可多次调用 `session.configure` 切换 lang（如先搜 en vault 再搜 ja vault），切换后后续工具调用按新 lang 解析。无需重连 MCP stream。
- **生命周期**：`session.configure` 设置的状态按 MCP stream 生命周期存活——绑定到该 stream，stream 关闭即丢弃，无持久化、无跨重连保留。
- **state 存放**：server 进程内按 MCP stream/session id 索引的内存 dict；不落盘，不进 SQLite。
- **lang 合法性**：`session.configure` 传入的 lang 必须是 workspace 已存在的 lang（indexer 启动时按 `$workspace/memory/languages/*/` 确定可用 lang 集合；运行时新 lang 发现机制见 memory-vault-search-spec.md「运行时新 lang 发现」）。**不在集合内时 session.configure 内部自动调 create_vault_tool 创建该 lang vault；创建失败（含非法 lang 名）返回错误。**
- **fs 工具**：path 相对会话 lang vault 根 `$workspace/memory/languages/$lang/vault/`，工具层强制校验解析后路径不逃出该 lang vault_dir（防 `../`）。
- **搜索类 fs 工具（grep / find）路径不存在语义**：`grep` 与 `find` 的搜索根路径不存在时，返回空结果（`{ "matches": [] }` / `{ "files": [] }`），不报 `isError=true`。便于 agent 在尚无该子目录时（如首个 vocab 条目写入前）执行查重搜索，自然走"未命中→新建"逻辑。同一约束不适用于 `ls`/`read`/`append`/`delete`——这些工具路径不存在仍是错误。
- **search 工具**：`lang` 参数可选，省略时取会话 lang；显式传入可覆盖会话 lang（支持一次跨 lang 检索）。

### vault 管理工具豁免

`list_vaults` 与 `create_vault` 是 workspace 级工具，不绑特定 lang：

- 不需要也不接受 `session.configure`（workspace 还没有任何 lang 时也得能创建第一个）。
- 不修改会话状态；返回里不含任何 session 级字段。
- 用于「发现现有 langs」与「创建新 lang vault + 同步注册到 indexer」。创建后 agent 再 `session.configure(lang=$lang)` 即可使用 fs / search 工具。

### Utility 工具豁免

`gen_id` 是纯计算工具，不绑特定 lang，同样豁免 `session.configure`：

- 直接调用，无需先调 `session.configure`。
- 不修改会话状态，不访问 vault 文件系统。
- 返回 26 字符 Crockford base32 ULID，适用于新条目 frontmatter `ulid` 与文件名 ulid 部分。


## 与 indexer 的关系

- **search 工具**：进程内直调 `search.py:do_search(conn, ...)`，按会话 lang 取对应 lang 的 SQLite RW 连接。**不经 HTTP/UDS**（MCP server 与 indexer 同进程，直调更高效）。HTTP `POST /{lang}/search` 端点保留供 gateway / CLI 等外部客户端使用，二者同源、行为一致。
- **fs 工具**：纯文件系统操作（读写 markdown），不碰 SQLite。与 indexer 的 watcher/indexer 模块解耦——watcher 监听文件变更自动入索引，fs 工具只读写文件内容。
- **indexer 不可达降级**：因 MCP server 内嵌于 indexer 进程，indexer 进程即 MCP server 进程，不存在「indexer 不可达」场景（同进程）。若 MCP 客户端连得上 MCP server，即 indexer 在线。


## 示例

### search 工具 - hybrid 混合搜索示例

转引自 [search-api-spec.md](/docs/impl-spec/search/search-api-spec.md)「##### 示例 3 - hybrid 混合搜索」。

hybrid 混合搜索，混合了全文搜索和语义搜索的结果。

请求（MCP 工具调用）:
```json
{
  "q": "god",
  "kind": "item",
  "mode": "hybrid",
  "limit": 4
}
```

等价的 HTTP 调用（外部客户端用）:
```bash
curl --unix-socket $workspace/indexer.sock http://localhost/en/search \
  -H 'Content-Type: application/json' \
  -d '{"q":"god","kind":"item","mode":"hybrid","limit":4}' | jq -r
```

响应:
```json
{
  "hits": [
    {
      "ulid": "01KWDVQ6GMWPNTMY4CBSNSCDBE",
      "kind": "item",
      "lang": "en",
      "item_type": "vocab",
      "file_path": "items/vocab/god--01KWDVQ6GMWPNTMY4CBSNSCDBE.md",
      "title": "\"god\" 释义",
      "score": 0.01639344262295082,
      "source": "hybrid",
      "chunk": null,
      "snippet": "# god\n\n## 给我的解释\n\n`god` 是英语名词，意为\"神、神灵\"，首字母大写 **God** 通常指一神论中的独一真神，小写 **god** 指多神教中的某一位神祇或比喻义。\n\n## 遇到记录\n\n- 2026-07-01：用户在学习英语时查询单词 god 并明确要求记住该单词的知识点。"
    },
    {
      "ulid": "01KWDVQ6GMWPNTMY4CBSNSCDBE",
      "kind": "item",
      "lang": "en",
      "item_type": "vocab",
      "file_path": "items/vocab/god--01KWDVQ6GMWPNTMY4CBSNSCDBE.md",
      "title": "\"god\" 释义",
      "score": 0.01639344262295082,
      "source": "hybrid",
      "chunk": {
        "chunk_id": 9,
        "section_title": "headword",
        "section_kind": "frontmatter",
        "char_offset": 0,
        "text": "headword: god"
      },
      "snippet": "headword: god"
    }
  ],
  "count": 2,
  "took_ms": 1056.846970001061
}
```

字段说明：混合了全文搜索、语义搜索的字段。

- `source: "hybrid"` 表示混合来源。
- `chunk` 字段：exact 模式为 `null`；semantic / hybrid 模式可能返回匹配到的块说明。
  - `section_kind`：`frontmatter`（markdown 文件 frontmatter）或其它（markdown 文件主体）。
  - `char_offset`：匹配块在 markdown 文件主体（不含 frontmatter）中的字符 offset；`section_kind=frontmatter` 时总为 0。
  - `text`：匹配块文本。
- `snippet`：匹配到的块文本（与 `chunk.text` 同源，exact 模式无 chunk 时取整文件摘要）。


### search 工具 - MCP 工具返回结构

上述 `search` 响应在 MCP 2025-11-25 协议下被包装为 `tools/call` 响应，携带 `content`（向后兼容的文本块）与 `structuredContent`（结构化结果，须与 `vault-mcp-spec-tools.yaml` 中 `search` 工具的 `outputSchema` 严格对齐）：

```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"hits\":[{\"ulid\":\"01KWDVQ6GMWPNTMY4CBSNSCDBE\",\"kind\":\"item\",\"lang\":\"en\",\"item_type\":\"vocab\",\"file_path\":\"items/vocab/god--01KWDVQ6GMWPNTMY4CBSNSCDBE.md\",\"title\":\"\\\"god\\\" 释义\",\"score\":0.01639344262295082,\"source\":\"hybrid\",\"chunk\":null,\"snippet\":\"# god\\n\\n## 给我的解释\\n\\n`god` 是英语名词，意为\\\"神、神灵\\\"，首字母大写 **God** 通常指一神论中的独一真神，小写 **god** 指多神教中的某一位神祇或比喻义。\\n\\n## 遇到记录\\n\\n- 2026-07-01：用户在学习英语时查询单词 god 并明确要求记住该单词的知识点。\"},{\"ulid\":\"01KWDVQ6GMWPNTMY4CBSNSCDBE\",\"kind\":\"item\",\"lang\":\"en\",\"item_type\":\"vocab\",\"file_path\":\"items/vocab/god--01KWDVQ6GMWPNTMY4CBSNSCDBE.md\",\"title\":\"\\\"god\\\" 释义\",\"score\":0.01639344262295082,\"source\":\"hybrid\",\"chunk\":{\"chunk_id\":9,\"section_title\":\"headword\",\"section_kind\":\"frontmatter\",\"char_offset\":0,\"text\":\"headword: god\"},\"snippet\":\"headword: god\"}],\"count\":2,\"took_ms\":1056.846970001061}"
      }
    ],
    "structuredContent": {
      "hits": [
        {
          "ulid": "01KWDVQ6GMWPNTMY4CBSNSCDBE",
          "kind": "item",
          "lang": "en",
          "item_type": "vocab",
          "file_path": "items/vocab/god--01KWDVQ6GMWPNTMY4CBSNSCDBE.md",
          "title": "\"god\" 释义",
          "score": 0.01639344262295082,
          "source": "hybrid",
          "chunk": null,
          "snippet": "# god\n\n## 给我的解释\n\n`god` 是英语名词，意为\"神、神灵\"，首字母大写 **God** 通常指一神论中的独一真神，小写 **god** 指多神教中的某一位神祇或比喻义。\n\n## 遇到记录\n\n- 2026-07-01：用户在学习英语时查询单词 god 并明确要求记住该单词的知识点。"
        },
        {
          "ulid": "01KWDVQ6GMWPNTMY4CBSNSCDBE",
          "kind": "item",
          "lang": "en",
          "item_type": "vocab",
          "file_path": "items/vocab/god--01KWDVQ6GMWPNTMY4CBSNSCDBE.md",
          "title": "\"god\" 释义",
          "score": 0.01639344262295082,
          "source": "hybrid",
          "chunk": {
            "chunk_id": 9,
            "section_title": "headword",
            "section_kind": "frontmatter",
            "char_offset": 0,
            "text": "headword: god"
          },
          "snippet": "headword: god"
        }
      ],
      "count": 2,
      "took_ms": 1056.846970001061
    },
    "isError": false
  }
}
```

要点（与 [MCP 2025-11-25 Tools Spec](https://modelcontextprotocol.io/specification/2025-11-25/server/tools#structured-content) 一致）：

- **`content[0].text`**：与 `structuredContent` 序列化后完全一致的 JSON 字符串。`text` 块必须存在——为旧客户端的向后兼容（[SHOULD](https://modelcontextprotocol.io/specification/2025-11-25/server/tools#structured-content)）。
- **`structuredContent`**：结构化结果对象，**MUST** 严格符合 `search` 工具的 `outputSchema`。客户端可对其做 JSON Schema 校验。
- **`isError: false`**：正常返回；执行错误（如 indexer 进程内 SQLite IO 错误、lang 未 configure、 lang 不在集合内）设为 `true`，此时 `content[0].text` 携带可读错误文本，`structuredContent` 可省略或为 `{}`。
- **失败响应示例**（未调用 `session.configure` 时）：
  ```json
  {
    "jsonrpc": "2.0",
    "id": 6,
    "result": {
      "content": [
        {
          "type": "text",
          "text": "session not configured: call session.configure first"
        }
      ],
      "isError": true
    }
  }
  ```

其它工具（`session.configure` / fs 工具集）的 `content` + `structuredContent` 形态与 `search` 同构，详见 [vault-mcp-spec-tools.yaml](vault-mcp-spec-tools.yaml) 各工具 `outputSchema`。


## Resources

（待补充）


## Server Instructions

MCP server 在 `initialize` 响应里通过 `instructions` 字段（[MCP 2025-11-25 Initialize](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/initialization) `InitializeResult.instructions`）向 agent 暴露一段**总览使用说明**，是 agent 拿到工具清单之前/同时可见的「服务器自述」。FastMCP 通过 `FastMCP(name=..., instructions=...)` 构造器参数注册；实现位于 `src/everlingo/mem/vault/mcp_server/mcp_server.py` 的模块级常量 `_SERVER_INSTRUCTIONS`。

**契约**：实现方维护的实际文本可调整措辞与排版，但**必须覆盖**以下最小内容清单（缺一即视为违反 spec）：

1. **服务器定位**——说明这是 Everlingo memory vault 的 MCP 接口、vault 是按学习语言分目录的 markdown 知识库。
2. **工具分组**——点明 `session.configure` / fs 工具集（10 个）/ `search` / vault 管理（2 个：`list_vaults`、`create_vault`）/ Utility（1 个：`gen_id`）五个分组；总工具数 15。
3. **强约束工作流**——
   - 调用任何 fs / `search` 工具前**必须**先调 `session.configure(lang=...)`；否则返回固定错误文案 `session not configured: call session.configure first`。
   - `lang` 必须是 workspace 已存在的语言目录（`$workspace/memory/languages/*/`）。
   - 会话内可重调 `session.configure` 切换 lang，无需重连。
    - 例外：`list_vaults` / `create_vault` / `gen_id` 是 workspace 级或 Utility 工具，**不**受上述 configure 约束。
4. **路径语义**——fs 工具的 `path` 参数相对会话 lang vault 根 `$workspace/memory/languages/$lang/vault/` 解析；`../` 越界被拒绝。
5. **search 要点**——默认 `mode=hybrid`（推荐）；`lang` 参数可省略或显式覆盖以跨 lang 检索；命中 `file_path` 可直接喂给 fs 工具。
6. **副作用说明**——文件变更由 indexer watcher 自动重新索引，agent **不需要**也**无法**手动触发 index。
7. **会话生命周期**——session 状态按 MCP stream 生命周期存活，stream 关闭即丢弃；无持久化。
8. **典型用法序列**——示例 `session.configure → search → read → append`，给 agent 一条参考路径。

实现方在修改实际文本时，必须保证上述 8 项要点均仍可从文本中检索到对应关键词或同义表述；如需变更要点本身，须同步更新本 spec 节。


## 工具调用 debug 日志

每次 MCP Server 工具调用均记录 debug 日志。契约如下：

- **适用范围**：全部 15 个工具（`list_vaults`、`create_vault`、`gen_id`、`session.configure`、10 个 fs 工具 `ls`/`read`/`write`/`append`/`grep`/`find`/`stat`/`mkdir`/`delete`/`tree`、`search`）的每次调用。
- **level**：`logging.DEBUG`。
- **logger**：`everlingo.mem.vault.mcp_server`（`logging.getLogger("everlingo.mem.vault.mcp_server")`），在 indexer 进程的 uvicorn log_config（`_run_indexer`）中独立挂 `file` handler + 强制 `level=DEBUG` + `propagate=False`，不随 `--log-level`（默认 `info`）浮动，保证工具调用 debug 日志稳定写入 `$workspace/logs/indexer.log`（见 [observability.md](/docs/impl-spec/observability.md)「进程与日志文件边界」）。
- **字段**：工具名（tool name）、输入参数（input）、输出结果（output / error）。
- **格式**：对齐 [chat-agent-tools-spec.md](/docs/impl-spec/chat-agent-tools-spec.md#tools-调用日志) 约定——

  **入口**（调用时立即记录）：
  ```
  tool_name: <name> , parameters: argName1=argValue1, argName2=argValue2, ...
  ```

  **正常出口**（调用返回后）：
  ```
  tool_name: <name> , return: <repr>
  ```

  **异常出口**（抛异常后，`isError=true` 响应返回前）：
  ```
  tool_name: <name> , parameters: argName1=argValue1, ... , error: <ExcType>: <msg>
  ```
  error 行携带 parameters 以提供一次性上下文，需与入口行靠日志 reader 去重。

- **参数过滤**：`ctx: Context` 参数（FastMCP 内部对象）不出现在日志中。
- **不截断**：`read.content`、`write.content`、`search.hits` 等大字段原样记录，不做截断或摘要。

实现方在 `src/everlingo/mem/vault/mcp_server/mcp_server.py` 内通过 `@_log_mcp_tool("<name>")` 装饰器（`create_mcp_app` 内本地定义的 async 装饰器）应用到各工具函数。装饰顺序为 `@mcp.tool`（外层） + `@_log_mcp_tool`（内层），确保 FastMCP 注册的是已包装的异步函数。

## 实现细节（增量）

下面是当前 `src/everlingo/mem/vault/mcp_server/` 实现与本 spec 的具体绑定方式，spec 本身只约束契约（工具名 / 入参 / 出参 / 错误形态），以下为实现层选择：

- **绑定**：`127.0.0.1:<OS 分配空闲端口>`（`pick_free_port`），写入 `$workspace/indexer.mcp.url`；indexer 退出时清理该文件。只绑 loopback（不暴露 LAN）。
- **进程并发**：主线程跑 FastAPI UDS server，daemon 子线程跑 MCP Streamable HTTP server（`run_mcp_server`），共享同一 `AppState`。
- **会话 id 来源**：`fastmcp.Context.session_id`（stream 级 UUID，stream 关闭即失效，state 不落盘）。
- **包结构**：MCP server 单独成包 `src/everlingo/mem/vault/mcp_server/`（与 `search/` 平级），因工具集不只 search，还含 fs 工具集 + session.configure。
- **错误文本**：FastMCP 默认在工具抛 `RuntimeError` 时把 `"Error calling tool '<name>': <msg>"` 写入 `content[0].text`；spec 强制 `text` 携带可读错误文本，此处前缀不破坏可读性，agent 端可按 substring 匹配真实错误。
- **FastMCP 版本**：`fastmcp>=2.0`（实际 3.x 系列，API 兼容本 spec 描述的 `add_tool` / `http_app(transport="streamable-http")`）。

### vault 管理工具实现绑定

- **`list_vaults`** 直接调 `workspace.lang_dirs()`，无需 AppState / session。返回 `{"vaults": [...], "count": N}`。
- **`create_vault`** 顺序：校验 lang 名（禁 `/`、`\`、`.`、`..`、空、NUL）→ `mkdir vault_root(parents=True, exist_ok=True)` → 幂等写 `VAULT_SPEC.md`（不存在才写；内容由 `everlingo.utils.md_prompt_compiler.compile_prompt("vault_spec.md", PackageSource(package="everlingo.mem.vault"))` 合成；**不** `shift_headings`，因为这是独立顶级文档）→ 同步调 `state._open_lang(lang)` 注册到 indexer（与 `LangDiscoveryWatcher` 同一入口，加锁幂等，失败不阻断）。返回 `{"ok": true, "lang, "vault_path": "memory/languages/$lang/vault", "created", "spec_written", "registered"}`。`vault_path` 取相对当前 workspace 根的路径。
- **VAULT_SPEC.md 不入索引**：由 indexer 端的 `is_excluded_vault_file(abs_path, memory_root)` helper（`src/everlingo/mem/vault/search/indexer.py`）统一排除 `VAULT_SPEC.md` 与 `tmp/` 子目录，调用方为 `walk_vault` / `sync.reconcile` / `watcher._dispatch`，避免在三个点各自重复排除规则。
