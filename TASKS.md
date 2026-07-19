# Current Sprint

## 进行中的任务

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"

- 2026-07-19 | **ADR**: 移除 Memory Extract Agent，Chat Agent 直接对接 Memory Writer Agent
  - `request_memory_extraction` 工具入参改为 `entries: list`（draft 仅含 LLM 字段：item_type/why_want_to_save_memory/title）
  - `MainAgent._pending_drafts` 替代 `_pending_extract`，支持一轮内多次工具调用累积
  - `MainAgent.invoke()` 末尾直接构造 MemoryEntry（补全系统字段）入队 Writer
  - 删除 `mem_extract_agent.py`；归档 `memory-extract-agent-spec.md`、`memory_extract_spec.md`
  - Chat Agent 通过按需 `vault_mcp_read(path="spec/memory_extract_output_spec.md")` 加载 entries 规范，不再静态注入 system prompt
  - 删除测试文件 `test_mem_extract_agent.py`；创建 `test_main_agent.py`（13 个用例）
  - 更新 `chat-agent-spec.md` / `memory-writer-agent-spec.md` / `chat-agent-tools-spec.md`
  - ADR 文档：`docs/ADR/20260719-remove_memory_extractor_agent.md`

- 2026-07-19 | **Bug 修复**：Chat Agent 无响应 — `dict` 下标访问 pydantic `_MemoryEntryDraft` 实例引发 `TypeError`
  - 根因：`request_memory_extraction` 工具按 `args_schema` 解析后产 pydantic 实例，`MainAgent.ainvoke()` 末尾用 `d["item_type"]`（dict 下标）访问，pydantic BaseModel 不支持 `__getitem__`
  - 修复：`agent.py` 改用属性访问 `d.item_type` / `d.why_want_to_save_memory` / `d.title`
  - `request_memory_extract.py`：`_MemoryEntryDraft` 字段类型收紧为 `Literal[...]`（与 ADR §4.1 对齐）
   - 测试用例从 dict 字面量改为 `_MemoryEntryDraft(...)` 实例，新增 `test_pydantic_drafts_regression` 回归测试
   - `session.py`：`_handle_user_message` / `_handle_system_notice` 包 try/except，ainvoke 异常不崩整个会话

- 2026-07-19 | **ADR**: 引入 `UserInputEnvelope` 统一结构化用户输入协议
  - 新增 `envelope.py`：`UserInputEnvelope` pydantic 模型（schema_version 1, task: translate/look_up/none, source tagged union: plain/web/pdf/epub/ios_app） + `wrap_plain_text()` + `render_envelope_to_message_text()`
  - `channel.py`：删除 `recv()` 抽象方法，新增 `recv_envelope()` 抽象方法
  - `stdio_channel.py` / `wechat_channel.py`：`recv()` → `recv_envelope()`，用 `wrap_plain_text()` 包装用户输入
  - `web_channel.py`：`recv()` → `recv_envelope()`，`_incoming` 队列类型改为 `UserInputEnvelope`
  - `web_acceptor.py`：`MessageBody` 改为 union（`text` / `envelope`），旧 `{text}` 自动包装
  - `session_events.py`：`UserMessage.text` → `UserMessage.envelope`
  - `session.py`：`_channel_listener` 调 `recv_envelope()`；`_handle_user_message` 渲染 envelope 后传给 `agent.ainvoke`；日志格式改为 `envelope={JSON}`
  - `agent.py`：system prompt 在 `## 用户意图分类` 前新增 `## 结构化用户输入（envelope）` 节
  - 新增 `tests/test_envelope.py`（14 用例）；更新 `test_web_channel.py` / `test_wechat_channel.py` / `test_web_acceptor.py` / `test_session_event_queue.py`
  - ADR 文档：`docs/ADR/20260719-envelope.md`；设计文档：`docs/impl-spec/envelope-spec.md`
  - 更新 `channel.md` / `session.md` / `chat-agent-spec.md` / `web-session-acceptor.md`

- 2026-07-19 | **用户交互日志**：在 Session 层记录所有用户输入与 Agent 回复文本（debug 级别，`[ChatAgent]` 前缀）
   - `session.py`：`_handle_user_message` 入口记 `[ChatAgent] IN`、出口记 `[ChatAgent] OUT`（逐条）；`_handle_system_notice` 同理记 `[ChatAgent] NOTICE IN` / `NOTICE OUT`
   - `session.md`：新增「交互日志」节，说明前缀、格式、日志级别
   - `observability.md`：在「Logging」节添加指引指向 session.md
   - `chat-agent-spec.md`：`Observability` 节增加用户交互 IO 日志的指引
