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
