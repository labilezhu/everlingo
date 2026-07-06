# Valut MCP Spec

基于 [MCP 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25) 规范， 实现一个 支持 [Streamable HTTP Transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports#streamable-http) 的 MCP Server 。

技术选型：使用 FastMCP 。

## 部署形态

本 MCP Server **内嵌于 indexer 进程**（方案 C：合并部署），与 indexer 的 HTTP/UDS REST API 共进程，监听不同端口：

- indexer 进程同时承载两个对外接口：
  1. HTTP over unix socket REST API（`$workspace/indexer.sock`，FastAPI/uvicorn）—— 现有 `/{lang}/search|index|delete|rebuild|embed`、`/status`，给 gateway / CLI 等外部客户端用。契约见 [search-api-spec.md](/docs/impl-spec/search/search-api-spec.md)。
  2. MCP 2025-11-25 Streamable HTTP Server —— 给 LLM agent / MCP 客户端用，暴露 fs 工具 + `search` 工具 + `session.configure` 工具。
- indexer 启动时把 MCP Streamable HTTP URL 写入 `$workspace/indexer.mcp.url` 文件，MCP 客户端据此连接。
- 进程拓扑见 [memory-vault-search-spec.md](/docs/impl-spec/search/memory-vault-search-spec.md)「进程拓扑」。

工具定义见 [valut-mcp-spec-tools.yaml](valut-mcp-spec-tools.yaml)。


## 会话 lang 机制

MCP Server 不在启动时绑定单一 lang；而是通过 `session.configure` 工具在会话内设定会话默认 lang（及其它会话级默认值）。设计要点：

- **必须先 configure**：agent 调用任何 fs 工具（ls/read/write/grep/find/stat/mkdir/delete/tree）或 `search` 工具之前，必须先调用 `session.configure` 设定会话 lang；否则上述工具返回错误 `session not configured: call session.configure first`。无隐式回退（不自动取 workspace 唯一 lang、不自动取 indexer 启动默认 lang）——强制显式，促使 agent 建立正确习惯。
- **可重调切换**：会话内可多次调用 `session.configure` 切换 lang（如先搜 en vault 再搜 ja vault），切换后后续工具调用按新 lang 解析。无需重连 MCP stream。
- **生命周期**：`session.configure` 设置的状态按 MCP stream 生命周期存活——绑定到该 stream，stream 关闭即丢弃，无持久化、无跨重连保留。
- **state 存放**：server 进程内按 MCP stream/session id 索引的内存 dict；不落盘，不进 SQLite。
- **lang 合法性**：`session.configure` 传入的 lang 必须是 workspace 已存在的 lang（indexer 启动时按 `$workspace/memory/languages/*/` 确定可用 lang 集合；运行时新 lang 发现机制见 memory-vault-search-spec.md「运行时新 lang 发现」）。不在集合内返回错误。
- **fs 工具**：path 相对会话 lang vault 根 `$workspace/memory/languages/$lang/vault/`，工具层强制校验解析后路径不逃出该 lang vault_dir（防 `../`）。
- **search 工具**：`lang` 参数可选，省略时取会话 lang；显式传入可覆盖会话 lang（支持一次跨 lang 检索）。


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

上述 `search` 响应在 MCP 2025-11-25 协议下被包装为 `tools/call` 响应，携带 `content`（向后兼容的文本块）与 `structuredContent`（结构化结果，须与 `valut-mcp-spec-tools.yaml` 中 `search` 工具的 `outputSchema` 严格对齐）：

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
- **`isError: false`**：正常返回；执行错误（如 indexer 进程内 SQLite IO 错误、lang 未 configure、lang 不在集合内）设为 `true`，此时 `content[0].text` 携带可读错误文本，`structuredContent` 可省略或为 `{}`。
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

其它工具（`session.configure` / fs 工具集）的 `content` + `structuredContent` 形态与 `search` 同构，详见 [valut-mcp-spec-tools.yaml](valut-mcp-spec-tools.yaml) 各工具 `outputSchema`。


## Resources

（待补充）


## 实现细节（增量）

下面是当前 `src/everlingo/mem/vault/mcp_server/` 实现与本 spec 的具体绑定方式，spec 本身只约束契约（工具名 / 入参 / 出参 / 错误形态），以下为实现层选择：

- **绑定**：`127.0.0.1:<OS 分配空闲端口>`（`pick_free_port`），写入 `$workspace/indexer.mcp.url`；indexer 退出时清理该文件。只绑 loopback（不暴露 LAN）。
- **进程并发**：主线程跑 FastAPI UDS server，daemon 子线程跑 MCP Streamable HTTP server（`run_mcp_server`），共享同一 `AppState`。
- **会话 id 来源**：`fastmcp.Context.session_id`（stream 级 UUID，stream 关闭即失效，state 不落盘）。
- **包结构**：MCP server 单独成包 `src/everlingo/mem/vault/mcp_server/`（与 `search/` 平级），因工具集不只 search，还含 fs 工具集 + session.configure。
- **错误文本**：FastMCP 默认在工具抛 `RuntimeError` 时把 `"Error calling tool '<name>': <msg>"` 写入 `content[0].text`；spec 强制 `text` 携带可读错误文本，此处前缀不破坏可读性，agent 端可按 substring 匹配真实错误。
- **FastMCP 版本**：`fastmcp>=2.0`（实际 3.x 系列，API 兼容本 spec 描述的 `add_tool` / `http_app(transport="streamable-http")`）。
