# Current Sprint

## 进行中的任务

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"

- 2026-07-11 20:00 | Phase 1 — 更新 vault spec 文件：memory_extract_spec.md 去 stale 引用；events_spec.md 事件格式更新（headword→title, 移除 mean_summary）；创建 vault_specs/default/mem_entry_spec.md；memory_extract_output_spec.md 改用 {{ include }} 引用 mem_entry_spec.md
- 2026-07-11 20:00 | Phase 2 — 更新 mem_entries.py：LLMGeneratedEntry 输出字段改为 item_type/why_want_to_save_memory/title；MemoryEntry 改为 title + new_messages/context_messages（移除 headword/mean_summary/conversation_context）
- 2026-07-11 20:00 | Phase 3 — 更新 mem_extract_agent.py：MCP runtime 读取 vault spec（IndexerOfflineError 回退 PackageSource）；_post_process 填充 new_messages/context_messages/title
- 2026-07-11 20:00 | Phase 4 — 更新 mem_writer_agent.py：写 kb item 先于 events；_parse_write_confirmation 返回 (files, summary, conv_ctx)；_format_event_section 用 title+conversation_context；Writer system prompt 新增 conversation_context 生成指引
- 2026-07-11 20:00 | Phase 5 — 更新 session_events.py/gateway.py/agent.py：SystemNotice 和通知相关字段 headword→title
- 2026-07-11 20:00 | Phase 6 — 删除旧位置 mem/agents/mem_entry_spec.md 和 mem_extract_output_spec.md
- 2026-07-11 20:00 | Phase 7 — 更新测试：writer 测试 28/28 pass，extract 测试 29/29 pass，session_event_queue 12/12 pass，agent_system_notice 12/12 pass
- 2026-07-11 20:00 | Phase 8 — 更新设计文档 memory-extract-agent-spec.md 和 memory-writer-agent-spec.md 反映实现变更
- 2026-07-11 22:12 | 为 vault MCP Server 新增 compile_prompt 工具：展开 vault 内 markdown 文件的 {{ include }} 指令；更新 vault-mcp-spec.md（工具数 15→16、调试日志范围、分组说明）、vault-mcp-spec-tools.yaml（新增工具定义）、mcp_server.py（工具实现+Server Instructions 更新）、测试覆写 4 个用例
- 2026-07-11 23:00 | mem_extract_agent.py 改用 MCP compile_prompt 加载 spec：_load_extract_spec_from_vault 用 compile_prompt 替代 read，一次调用即可展开 include 链（memory_extract_spec.md → memory_extract_output_spec.md → mem_entry_spec.md）；移除 _load_extract_spec_from_package 与 PackageSource 兜底；修复 memory_extract_spec.md 缺少空行导致 include 未独立成段的问题；更新测试适配新签名与 mock；同步更新 memory-extract-agent-spec.md
- 2026-07-12 16:00 | 修复因 vault_spec.md 迁移至 vault_specs/default/ 导致的 3 个失败测试：test_mem_extract_agent.py 的 _demote_headings → shift_headings 导入修正、test_md_prompt_compiler.py 的 PackageSource 路径与内容断言更新、test_mem_vault_mcp_server.py 的 kb_items_spec.md → kb_items_spec_vocab.md 引用修正
