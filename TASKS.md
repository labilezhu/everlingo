# Current Sprint

## 进行中的任务

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"

- 2026-07-12 19:30 | Memory Writer Agent system prompt 的 mem_entry_spec.md 加载方式从 PackageSource 改为 MCP compile_prompt（与 Extract Agent 一致）
  - 新增 `_load_mem_entry_spec_from_vault(lang)` 镜像 `_load_extract_spec_from_vault`
  - `_build_writer_system_prompt()` 改为取参数，不再本地编译 spec
  - `_write_kb_item_async` per-entry 调 MCP 加载 spec 后构建 prompt
  - 更新测试：新增 `mem_entry_spec_text` fixture、autouse `_patch_mem_entry_spec`
  - 更新 memory-writer-agent-spec.md 设计文档

- 2026-07-12 17:00 | Chat Agent 显式驱动 Memory Extract Agent（而非每轮无条件触发）
  - 新增 `request_memory_extraction` 工具（tool def + factory），Chat Agent 通过 LLM 工具调用决定是否触发抽取
  - `ExtractInput` 新增 `reason` / `note` 字段，`WhySave` 新增 `Chat Agent 判定` 枚举
  - `MainAgent.invoke()` 改为条件 submit：工具调用设置 `_pending_extract` 标记，invoke 末尾统一切片提交
  - 未触发时游标仍推进，未触发轮自然成为后续 context_messages
  - Extract Agent 移除"应保存"语义筛选，改为信任上游 `reason` 映射为 `why_want_to_save_memory`
  - Extract Agent 保留结构性跳过规则（字数上限、来源边界、target_lang 无关）
  - system prompt 新增"记忆抽取触发"节，明确 LLM 何时调用工具
  - 更新 vault spec：`memory_extract_spec.md`（移除语义筛选）、`mem_entry_spec.md`（新增枚举值）
  - 更新设计文档：chat-agent-spec.md、memory-extract-agent-spec.md、chat-agent-tools-spec.md
  - 更新测试：新增 `test_no_tool_call_does_not_submit`、`test_pending_extract_triggers_submit`、`test_cursor_advances_even_without_submit`

