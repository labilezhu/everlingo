# Current Sprint

## 进行中的任务

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"

- 2026-07-13 10:00 | 补齐笔记删除/编辑功能的设计文档
  - chat-agent-spec.md：意图类型清单新增 #9 笔记删除 / #10 笔记编辑；重写「## 编辑笔记」节为「## 笔记删除与编辑」（含主流程、同步语义、约束、手工测试用例）；Agent tools 节新增 memory_writer_action 小节
  - chat-agent-tools-spec.md：新增「## 笔记删除与编辑 - memory_writer_action」工具集（operation/file_path/body 入参、返回 JSON、调用准则、同步实现机制、与 request_memory_extraction 的区别）
  - memory-writer-agent-spec.md：顶部补一句 delete/edit 不调 LLM；新增「## 笔记删除与编辑（同步 action 流程）」节（入口 execute_action_async、_ActionRequest、并发模型、delete/edit 路径、审计事件、不发 SystemNotice、离线降级、测试参考）
  - session.md：注明 delete/edit 不发 SystemNotice；修正 SystemNotice 字段名 headword→title
  - events_spec.md：补 action: edited 取值说明，并标注删除/编辑事件字段集与创建事件的差异
  - mem_entry_spec.md：补 delete/edit entry 来源说明与 title 占位语义

- 2026-07-12 19:30 | Memory Writer Agent system prompt 的 mem_entry_spec.md 加载方式从 PackageSource 改为 MCP compile_prompt（与 Extract Agent 一致）
  - 新增 `_load_mem_entry_spec_from_vault(lang)` 镜像 `_load_extract_spec_from_vault`
  - `_build_writer_system_prompt()` 改为取参数，不再本地编译 spec
  - `_write_kb_item_async` per-entry 调 MCP 加载 spec 后构建 prompt
  - 更新测试：新增 `mem_entry_spec_text` fixture、autouse `_patch_mem_entry_spec`
  - 更新 memory-writer-agent-spec.md 设计文档

- 2026-07-12 21:30 | Chat Agent 删除/编辑笔记条目（同步调用 Memory Writer Agent）
  - 数据结构扩展：mem_entry_spec.md 新增 operation / file_path / body 字段；events_spec.md 新增 action + file_path 字段；MemoryEntry 模型同步扩展
  - MemoryWriterAgent 新增 _ActionRequest + execute_action_async（public API）复用 daemon thread 串行执行 delete/edit，无锁
  - 新增 _delete_entry_async（stat→read→delete→events）和 _edit_entry_async（read→split frontmatter→write→events），纯代码无 LLM
  - 新增 _format_action_event_section / _append_action_event_async 记录 delete/edit 审计事件
  - _run_loop 新增 _ActionRequest 分发
  - 新建 memory_writer_action.py 工具工厂，Chat Agent 同步 await 调用
  - agent.py system prompt 新增"笔记删除与编辑"节（含确认流程约束）
  - _refresh_agent_if_needed 注入 memory_writer_action 工具
  - 13 项新增测试覆盖 delete/edit 核心流程与 daemon thread 分发

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

