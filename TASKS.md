# Current Sprint

## 进行中的任务
- 2026-07-07 (vault-readonly) | Chat Agent 记忆库只读查询：为 MainAgent 添加 vault MCP 长连接 + 5 个只读工具（search/read/ls/find/grep），invoke → ainvoke（async），Session.run 适配，Indexer 离线降级，更新 spec 文档（chat-agent-spec.md / chat-agent-tools-spec.md）。

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"
- 2026-07-06 22:30 | Bug fix: grep / find 工具路径不存在时返回空结果而非 isError 报错（`mcp_server.py`），避免 Memory Writer Agent 在首次写入某子目录时因查重 grep 报错中断流程。同时更新 spec 文档与增加测试覆盖。
- 2026-07-06 23:00 | 修复 MCP Server 工具调用 debug 日志被 indexer 进程默认 `--log-level=info` 过滤未落盘的问题。`mcp_server.py:36` logger 名改为显式 `"everlingo.mem.vault.mcp_server"`；`server.py:534-536` log_config 追加独立 handler + 强制 DEBUG + 不 propagate，确保工具调用 debug 日志稳定写入 `indexer.log`。同步修 spec 中错误的目标文件（everlingo.log → indexer.log）。chat-agent 端发现 `voice_speak` 缺 `@log_tool_call` 装饰器，已补加。更新 `observability.md` 补充进程-日志边界说明。
- 2026-07-07 10:00 | 将本地 `mem_gen_id` ULID 工具从 `mem_writer_mcp_client.py` 迁移到 MCP Server（`mcp_server.py` 新增 `gen_id` 工具，workspace 级豁免 session.configure）；同步删除客户端本地实现，更新 `mem_writer_agent.py` system prompt 工具名与 `WANTED_TOOLS`；更新 spec 文档（`vault-mcp-spec.md`/`vault-mcp-spec-tools.yaml`/`memory-writer-agent-spec.md`）与测试覆盖。
- 2026-07-07 10:20 | 修复因 `mem_writer_agent.py` system prompt 修改（entry 标题变更、vault_spec 注释移除）导致的 6 个 unit test 失败：更新 `test_mem_writer_agent.py` 中对应断言以匹配当前 prompt 内容。
