# Memory Writer Agent

负责写入 [memory vault](/docs/impl-spec/worksplace/memory-vault-spec.md) 。

Memory Writer Agent 负责验证、合并 Chat Agent 构造的 entries，并写入 memory vault 。

除"创建/合并笔记"主流程外，Writer 还接收 Chat Agent 同步触发的"删除 / 编辑"请求，**走代码路径，不调 LLM**（见下文「笔记删除与编辑」节）。

Memory Writer Agent 用一个队列接收请求，然后**异步**处理。Memory Writer Agent 是全局单例和独立单线程或协程。由于使用独立单线程或协程，所以没有并发写文件问题。队列内容不需要持久化，可接受因程序非法结束的丢失。

即，用独立 daemon Thread + queue.Queue 。

单例归属：放 src/everlingo/gateway/gateway.py 模块级实例。

**实现形态（2026-07 迁移）**：所有 vault 文件操作改走 [Vault MCP Server](/docs/impl-spec/vault-mcp/vault-mcp-spec.md)（indexer 进程内嵌的 FastMCP Streamable HTTP server）；MCP URL 从 `$workspace/indexer.mcp.url` 发现。indexer 离线时，entry 被丢弃并 `logger.error` 告警，不重试、不阻塞队列。


## 输入
见： [Memory Entry 结构说明](/src/everlingo/mem/vault/templates/default/spec/mem_entry_spec.md) 。

Chat Agent 在 `MainAgent.invoke()` 末尾为每条 entry 填充 `chat_session_id` / `entry_id` / `timestamp` / `channel_name` / `lang` / `interface_language` 等系统字段；Writer Agent 不应自行生成或改写这些字段。


## 处理 Memory Entry

写入 [memory vault](/docs/impl-spec/worksplace/memory-vault-spec.md)
1. 记录 [events](/src/everlingo/mem/vault/events_spec.md) 。
2. 更新 知识点类 memory items

日志要求：每次写文件，都需要有 info 级别的日志输出，描述写了什么文件，什么内容。

### 记录 events 的实现

events/ 的追加不该走 LLM。 

events_spec.md 是按日期 markdown 文件追加，纯结构化追加。让 LLM 去 read→modify→write 当天 events 文件性价比很低，且增加幻觉/格式错误风险。所以：
- events/ 写入用代码通过 MCP `stat`+`write`/`append` 工具追加 markdown 段落。
  - `stat(rel_path)` 判断文件是否存在
  - 不存在 → `write(rel_path, _EVENT_FILE_PREAMBLE)` 创建带前置内容的 markdown 文件
  - 存在或刚创建 → `append(rel_path, section + "\n")` 追加 `## Event` 段落

MCP `write` 工具在落盘前会调用 `normalize_frontmatter_text` 归一化 frontmatter（events 文件无 frontmatter，函数直接返回原文；该归一化主要保护 kb item 写入场景）。

### 更新 知识点类 memory items

1. 根据 `目标学习语言` / 知识类型 / 查找 memory vault 中是否已记录。可以找类似 grep 命令的方法找文件内容关键字。
2. 如已记录则合并，如未记录则创建 ；
3. 更新知识点 markdown 文件。对于目标  markdown 文件，llm 只调用一次 `read_file` 工具，llm 只调用一次 `write_file`  工具。
   1. 追加 `遇到记录`；
   2. 更新 frontmatter ；
   3. 根据 [kb_items_spec.md](/src/everlingo/mem/vault/kb_items_spec.md) 对应 知识类型 的正文格式和段落要求，更新 markdown 文件正文内容

## 笔记删除与编辑（同步 action 流程）

由 Chat Agent 的 `memory_writer_action` 工具同步触发，**不经过** Memory Extract Agent，Writer 端走纯代码路径（不调 LLM）。详见 [chat-agent-spec.md — 笔记删除与编辑](/docs/impl-spec/chat-agent-spec.md#笔记删除与编辑) 与 [chat-agent-tools-spec.md](/docs/impl-spec/chat-agent-tools-spec.md)。

### 入口与并发模型

Public API：`MemoryWriterAgent.execute_action_async(entry: MemoryEntry) -> dict`。

- 工具调用方构造 `MemoryEntry(operation="delete"|"edit", file_path=..., body=...)` 并 `await` 此方法。
- 内部将 `_ActionRequest(entry, future)` 入队后 `await asyncio.wrap_future(future)`，**30s 超时**保护（防止 daemon thread 被前序 LLM 写入阻塞过久）。
- `_ActionRequest` 数据结构（Writer 内部）：
  ```python
  @dataclass
  class _ActionRequest:
      entry: MemoryEntry
      future: concurrent.futures.Future
  ```
- **复用同一 daemon thread + `queue.Queue`**：`_run_loop` 按 item 类型分发 —— `_ActionRequest` 走 `_process_action`，`list[MemoryEntry]`（Extract Agent 入队）走 `_process_batch`。delete/edit 与 create 串行执行，**无需加锁**。
- daemon thread 在 `_process_action` 中 `asyncio.run(self._execute_action_async(entry))`：成功 → `future.set_result(result_dict)`；失败 → `future.set_exception(exc)`，由 Chat Agent 工具体 await 时抛出并转告用户。

### 输入字段

delete/edit 的 `MemoryEntry` 由 Chat Agent 的 `memory_writer_action` 工具构造（见 [mem_entry_spec.md](/src/everlingo/mem/vault/templates/default/spec/mem_entry_spec.md)）：

- `operation`：`"delete"` / `"edit"`
- `file_path`：必选，相对 vault 根路径（如 `items/vocab/aimai--01JZABD123.md`）
- `body`：`operation="edit"` 时必选，新 markdown 正文（不含 frontmatter YAML 段）
- `frontmatter`：`operation="edit"` 时可选的完整 frontmatter YAML 文本。保护字段会被强制保留原值（见 edit 路径）
- 系统字段由工具工厂填充：`entry_id=uuid4()`、`timestamp=now`（GMT+8 `%Y-%m-%d %H:%M:%S`）、`lang=target_lang`、`interface_language`、`chat_session_id`、`channel_name`
- `item_type` / `title` 在 entry 中仅为占位（默认 `"others"` / `""`）；真实值由 Writer 从文件 frontmatter 回读后放入返回结果

### delete 路径：`_delete_entry_async`（纯代码，no LLM）

1. `file_path = _normalize_path(entry.file_path or "")`（去前导 `/`）；空 → `{"ok": False, "error": "file_path is required"}`
2. `async with mcp_vault_connection(entry.lang) as (session, _tools):`
   - `stat(path=file_path)` → 不存在 → `{"ok": False, "error": "file not found", "file_path": ...}`
   - `read(path=file_path)` → `parse_frontmatter(content)` 取 frontmatter dict（用于写 events + 返回 title/item_type）
   - `delete(path=file_path)` → 失败 → `{"ok": False, "error": "delete failed: ..."}`
3. `await _append_action_event_async(entry, "deleted")`（失败被吞，只 `logger.exception`，不影响主结果）
4. 返回 `{"ok": True, "file_path", "title", "item_type"}`（title/item_type 来自原 frontmatter，缺失时回退到 entry 占位值）

### edit 路径：`_edit_entry_async`（纯代码，no LLM）

1. 同上校验 `file_path`；`not entry.body` → `{"ok": False, "error": "body is required for edit operation"}`
2. `async with mcp_vault_connection(entry.lang) as (session, _tools):`
   - `read(path=file_path)` → 失败 → `{"ok": False, "error": "read failed: ..."}`
   - `split_frontmatter(content)` 取原始 frontmatter 文本；`parse_frontmatter(content)` 取 dict
   - **frontmatter 合并逻辑**：
     - 若 `entry.frontmatter` 为空/None → 保留原 frontmatter 原样（与旧行为一致）
     - 若提供了 `entry.frontmatter`：
       1. `tolerant_parse(entry.frontmatter)` 解析 LLM 传入的 frontmatter dict
       2. `merged = {**original_fm, **llm_fm}`（LLM 字段覆盖原文件）
       3. 对以下**保护字段**强制用原文件值回填（不信任 LLM）：
          `ulid`, `slug`, `type`, `created_at`, `timestamp`, `schema_version`, `first_seen`, `last_seen`, `seen_count`
       4. `dump_frontmature(merged)` 重新序列化为合法 YAML
       5. `new_content = f"---\n{merged_fm}\n---\n{entry.body}"`
   - `write(path=file_path, content=new_content)`（server 端 `normalize_frontmatter_text` 会再归一化）→ 失败 → `{"ok": False, "error": "write failed: ..."}`
   - 合并后 `entry.title` 更新为 `merged.title`，审计事件用新 title
3. `await _append_action_event_async(entry, "edited")`
4. 返回 `{"ok": True, "file_path", "title"（合并后新title）, "item_type"}`

### 审计事件

复用当日 events 文件 `events/<YYYY>/<MM>/<YYYY-MM-DD>.md`，由 `_format_action_event_section(entry, action)` 生成 `## Event` 段落，`_append_action_event_async(entry, action)` 追加（流程与创建事件的 `_append_event_async` 一致：`stat` → `write` preamble 或 `append` section）。

字段（见 [events_spec.md](/src/everlingo/mem/vault/templates/default/spec/events_spec.md) 删除/编辑事件节）：
- `action`: `"deleted"` / `"edited"`
- `timestamp` / `lang` / `title` / `item_type` / `file_path` / `chat_session_id` / `channel_name`

**不包含** `why_want_to_save_memory` / `new_messages` / `context_messages` / `conversation_context`（这些是创建事件独有字段）。

### 不发 SystemNotice

与创建流程不同，delete/edit **不调用** `notice_sink.notify(...)`。结果通过 `future` 同步回 Chat Agent 的 `memory_writer_action` 工具体，由 LLM 直接转告用户。详见 [session.md](/docs/impl-spec/session.md) 中关于 SystemNotice 源的说明。

### 离线降级

MCP 连不上（`IndexerOfflineError`）时，异常通过 `future.set_exception` 回传；Chat Agent 工具体 `await` 时抛出，由 LLM 转告用户。**不丢弃 entry**（与创建流程的"丢弃+告警"不同），因为同步调用必须给用户反馈。

### 测试参考

`tests/test_mem_writer_agent.py`：
- `TestActionDelete` — `_delete_entry_async` 各场景（删除成功 / 文件不存在 / 写事件 / 缺 file_path）
- `TestActionEdit` — `_edit_entry_async` 各场景（保留 frontmatter / 缺 body / 文件不存在 / 写事件 / 缺 file_path）
- `TestActionDaemonDispatch` — `_ActionRequest` 经 `_run_loop` 分发与 future 回传

## 实现
应实现于： `/src/everlingo/mem/agents/mem_writer_agent.py`。

用 langchain 的 agent 框架。有自己的 system prompt 。

**vault 访问层**：通过 MCP server 完成，见 `src/everlingo/mem/agents/mem_writer_mcp_client.py`。
- `mcp_vault_connection(lang)` — 异步上下文管理器，per-entry 打开一条 MCP stream，调用 `session.configure` 设定会话 lang，yield `(session, tools)`。
- `tools` 为 langchain `BaseTool` 列表（来自 `load_mcp_tools(session)` 过滤后的子集，含 MCP `vault_mcp_gen_id` 工具——由 server 端 `gen_id` 经前缀加载）。
- 客户端到 MCP server 的传输用 `langchain-mcp-adapters` 的 `MultiServerMCPClient`。
- `IndexerOfflineError`：indexer 未启动 / URL 文件不存在 / 连不上 MCP server 时抛出；调用方捕获后丢弃 entry + `logger.error` 告警。

**writer 内部流程**：每条 entry 走 `asyncio.run(self._write_kb_item_async(entry))`：
1. `async with mcp_vault_connection(entry.lang) as (_session, tools):`
2. `create_agent(self._llm, tools=tools, system_prompt=...)` per-entry 构建
3. `await agent.ainvoke({"messages": [SystemMessage, HumanMessage]})`

**events 写入**：每条 entry 走 `asyncio.run(_append_event_async(entry))`：
1. `async with mcp_vault_connection(entry.lang) as (session, _tools):`
2. `stat` → `write`(preamble) 或 `append`(section)
3. 退出 with 后 `logger.info("events: created/appended ...")`

### 写入确认通知（2026-07）

`_write_kb_item_async` 写完每个 entry 后，从 LLM 最终 AIMessage 中解析写入确认 JSON：

```json
{
  "updated_files": ["items/vocab/ufo.md"],
  "update_summary": "简要描述本次更新内容"
}
```

确认由 Writer system prompt 中的 `## 写入完成确认` 节约束。解析成功且 `notice_sink` 已注入时，
Writer 调用 `notice_sink.notify(...)` 将通知路由到对应 Session。

通知内容包含：vault 文件路径列表、更新概要、title（记忆条目标题）、lang。Chat Agent 收到后决定是否告知用户。
session 不存在时丢弃（与 daemon thread "可接受丢失"语义一致）。

详见：
- [session.md — 系统事件源](/docs/impl-spec/session.md)
- `src/everlingo/gateway/session_events.py`

### System prompt
System prompt 需要包括 src/everlingo/mem/vault/vault_spec.md ，因为需要告诉 Agent memory vault 的结构 。这个文件中有 `{{ include [参考 kb_items_spec.md](./kb_items_spec.md) }}` 的包含引用部分。使用 src/everlingo/utils/md_prompt_compiler.py 的  `PackageSource` 来处理 markdown 文件运行期合并问题。

System prompt 还需要包括 `mem_entry_spec.md` ，用于告知 Agent 其输入 entry 的完整字段结构与字段含义（字段补充说明）。通过运行期调 MCP `compile_prompt` 工具从 vault 动态加载 `spec/mem_entry_spec.md`（含 include 展开），与 Extract Agent 的 spec 加载方式一致。不再通过本地 `PackageSource` 加载。

System prompt 同样需要包括 `spec/envelope_spec.md`，用于告知 Agent `new_messages` 与 `context_messages` 字段中 `<envelope>{JSON}</envelope>` 包装格式的 schema。通过同一条 MCP session 调 `compile_prompt` 加载 `spec/envelope_spec.md`（与 mem_entry_spec 共用一条连接，减少开销）。

注入 `mem_entry_spec.md`、`envelope_spec.md` 与 `vault_spec.md` 前，需用 `md_prompt_compiler.shift_headings(doc, 2)` 整体平移标题 +2 级，使其最浅标题 h1 → h3，嵌套于外层 `## 输入 entry 结构` / `## 输入消息的 Envelope 格式` / `## memory vault 结构` (h2) 之下。此约定与 `chat-agent-spec.md` 中「*.md 注入需降级标题」一致。`compile_prompt` 内部的 `context_level` 机制只调整 include 子文件标题，不调整入口文件自身标题，故需 `shift_headings` 在编译输出上额外平移。

注入位置顺序（自上而下）：
1. `## 输入给你的 entry 结构` — 说明 entry 整体字段
2. `## 输入消息的 Envelope 格式` — 说明 new_messages / context_messages 中消息的 Envelope schema
3. `# memory vault 注意事项` 及其子节 — vault 操作规范

另外，system prompt 需包含一段「语言配置」说明，明确告诉 Agent 两个语言字段的来源与用途：

- `目标学习语言`：来自 entry 的 `lang` 字段（语言代码，如 `ja`、`en`），表示用户正在学习的语言。kb item 中对该语言的引用（title、词形、例句）必须使用该语言本身书写。
- `界面语言`：来自 entry 的 `interface_language` 字段（语言代码，如 `zh-CN`），表示用户界面使用的语言。memory vault 中 markdown 文件正文（释义、记忆钩子、conversation_context 等）必须主要使用界面语言编写。

两个字段值由 Memory Extract Agent 在上游填充，Writer Agent 直接采用，不要自行推断或改写。

另外，system prompt 需包含一段「conversation_context 生成」说明，指导 LLM 根据 Memory Entry 中的 `new_messages` 和 `context_messages` 字段（渲染后的消息文本列表），在写入 kb item 的 `### conversation_context` 节时综合生成一段总结。`conversation_context` 应自然衔接这些消息的上下文（包括 Assistant 的回复），而非仅罗列用户输入。


### 写入完成确认

LLM 在完成所有文件写入后，最终 AIMessage 应输出结构化 JSON 确认，格式：

```json
{
  "updated_files": ["items/vocab/ufo.md"],
  "update_summary": "新建词条 ufo，含释义与例句"
}
```

- `updated_files`：本次写入/修改的所有 vault 文件相对路径列表
- `update_summary`：一句话概述更新内容，使用 entry 的 interface_language
- 不输出其他文字
- 写入失败（无需写入确认）时回复空内容

此约束写入 system prompt 的 `## 写入完成确认` 节。

### Agent tools
所有文件和目录操作都通过 [Vault MCP Server](/docs/impl-spec/vault-mcp/vault-mcp-spec.md) 暴露的 fs 工具完成。MCP URL 从 `$workspace/indexer.mcp.url` 文件发现（indexer 启动时写入）。

工具沙箱：所有 fs 工具都"只能用相对 path，假设当前目录位于 `$workspace/memory/languages/$lang/vault/`"。MCP server 端强制校验：解析后路径不能逃出该 lang 的 vault_dir（防 `../`）。否则 LLM 一次幻觉就写到 vault 外。`session.configure(lang)` 由 writer 宿主代码在每个 entry 开始时自动调用，agent 无需主动 configure。

工具名（取自 MCP server 暴露的 fs 工具 + 客户端工具）：

- `read(path)`	读取文件。返回文本文件内容。
- `write(path, content)`	覆盖写入或新建文件。落盘前服务端自动调 `normalize_frontmatter_text` 归一化 frontmatter。返回写入结果。
- `append(path, content)`	追加写入或新建文件（要求文件已存在；events 流程的首次创建由 `write` 完成）。返回写入结果。
- `delete(path)`	删除文件。返回写入结果。
- `ls(path, recursive=False)`	列出指定目录下的文件或目录。返回格式： `[{name, path, type, size_bytes}]`
- `find(pattern, path="")`	按文件名 glob 搜索，目录递归。pattern 支持 `*` 等通配符。返回格式： `[{file_path, is_dir}]`, file_path 为相对 path 的相对路径。
- `grep(query, path="", ignoreCase=True)`	按内容正则搜索，目录递归。返回格式： `[{file_path, matched_text, line_number}]`。
- `vault_mcp_gen_id()` 返回类似 01JZABD123 格式的 随机 id（26 字符 ULID）。MCP server 暴露的纯计算 ULID 工具（workspace 级，豁免 session.configure）。可用于 markdown 文件名部分。
