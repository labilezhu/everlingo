# Current Sprint

## 进行中的任务

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"
- 2026-06-28 | Memory Extract Agent 改用独立 LLM 工厂 `create_extract_llm()`，temperature=0 以保证抽取任务的结构化输出确定性。改动：`src/everlingo/llm.py` 新增 `create_extract_llm()`（同 model/callbacks/tracing，仅 temperature=0）；`src/everlingo/mem/agents/mem_extract_agent.py` 切换 import 与调用；`docs/impl-spec/memory-extract-agent-spec.md` 同步更新「已知简化 / 待评估」段落标注已实施独立配置。`create_llm()` 保持 temperature=0.7 不变，主对话语气不受影响。
- 2026-06-28 | Memory Extract Agent 会话内 dedup 重构：废弃不稳定的 `session_seen_headwords` headword 字符串匹配（同一段历史被反复抽取且两次 headword 不一致），改为 `new_messages` / `context_messages` 输入侧硬隔离。`MainAgent` 持有 `_extract_cursor` 游标，每次 invoke 末尾切片：`new_messages = _messages[cursor:]`（唯一抽取来源）、`context_messages = _tail_recent_turns(_messages[:cursor], limit=19)`（仅供 `conversation_context`）。游标在 submit 前即推进，extract 失败也不再重抽本轮。`ExtractInput` 调整为 `new_messages` + `context_messages` 两字段；`MemoryExtractAgent` 自身完全无状态；system prompt 新增"抽取边界硬约束"。改动文件：`docs/impl-spec/memory-extract-agent-spec.md`、`src/everlingo/mem/agents/mem_entries.py`、`src/everlingo/mem/agents/mem_extract_agent.py`、`src/everlingo/agents/agent.py`、`tests/test_mem_extract_agent.py`。236 tests passed。
