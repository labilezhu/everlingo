# Current Sprint

## 进行中的任务

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"

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

