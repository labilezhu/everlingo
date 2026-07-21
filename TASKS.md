# Current Sprint

## 进行中的任务

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"
2026-07-20 20:00 | Chat Agent 提交 mem_entry 添加 DEBUG 日志（create + delete/edit 两路径）- 全量 model_dump
2026-07-20 21:00 | Memory Writer Agent system prompt 注入 envelope_spec.md，解释 new_messages / context_messages 中的 Envelope 格式；重构为共用一条 MCP session 加载两个 spec
2026-07-21 10:00 | Standalone Web Chatbot 加入 task 单选按钮（翻译/查词/聊天），迁移到 envelope 结构化协议；更新相关设计文档
2026-07-21 11:00 | Chat Agent envelope 改为运行期 MCP compile_prompt 加载（与 Memory Writer 一致）；意图识别节新增 envelope.task 作用说明；_call_compile_prompt 迁移到共享的 mem_writer_mcp_client
2026-07-21 12:00 | 修复 7 个测试文件中的 20+ 个失败用例：agent.ainvoke 改用 AsyncMock（test_mem_writer_agent / test_agent_system_notice / test_gateway）；_disable_embedding autouse fixture（conftest.py）；LLM ainvoke try/except（agent.py）；assertions 更新（test_unified_agent.py）；channel.send_sound AsyncMock（test_voice_tool.py）；_cleanup_everlingo_handlers 防止日志处理器泄露（test_log_utils.py）

