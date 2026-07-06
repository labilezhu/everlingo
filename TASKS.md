# Current Sprint

## 进行中的任务


## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"
- 2026-07-06 22:30 | Bug fix: grep / find 工具路径不存在时返回空结果而非 isError 报错（`mcp_server.py`），避免 Memory Writer Agent 在首次写入某子目录时因查重 grep 报错中断流程。同时更新 spec 文档与增加测试覆盖。
- 2026-07-06 23:00 | 修复 MCP Server 工具调用 debug 日志被 indexer 进程默认 `--log-level=info` 过滤未落盘的问题。`mcp_server.py:36` logger 名改为显式 `"everlingo.mem.vault.mcp_server"`；`server.py:534-536` log_config 追加独立 handler + 强制 DEBUG + 不 propagate，确保工具调用 debug 日志稳定写入 `indexer.log`。同步修 spec 中错误的目标文件（everlingo.log → indexer.log）。chat-agent 端发现 `voice_speak` 缺 `@log_tool_call` 装饰器，已补加。更新 `observability.md` 补充进程-日志边界说明。
