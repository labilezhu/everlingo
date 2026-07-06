# Current Sprint

## 进行中的任务


## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"

- 2026-07-06 | MCP Server 全部 14 个工具调用加入 debug 日志（tool name / input / output）：
  - spec `vault-mcp-spec.md` 新增独立节「工具调用 debug 日志」，约定格式、level、logger、不截断大字段、错误也记 debug
  - `mcp_server.py` 新增 `_log_mcp_tool` async 装饰器 + `_format_tool_params` 辅助函数（skip `ctx`），应用到全部 14 个工具
  - 已有 20 例测试全部通过，无回归
  - 改动：`src/everlingo/mem/vault/mcp_server/mcp_server.py` ; `docs/impl-spec/vault-mcp/vault-mcp-spec.md`
- 2026-07-06 | 迁移 Memory Writer Agent 从本地 fs 工具到 Vault MCP Server：
  - MCP server `write` 工具新增 frontmatter 归一化（防 LLM 写坏 YAML 致下游解析失败）
  - 新增 `src/everlingo/mem/agents/mem_writer_mcp_client.py`：`mcp_vault_connection` per-entry 异步上下文 + 客户端 `mem_gen_id` ULID 工具 + `IndexerOfflineError`
  - `mem_writer_agent.py` 改 async（per-entry `asyncio.run`），`mcp_vault_connection` 包 per-entry MCP stream + `session.configure`；`_append_event_async` 通过 MCP `stat`+`write`/`append` 实现；`_process_batch` 捕获 `IndexerOfflineError` 丢弃 entry + `logger.error` 告警
  - 删 `src/everlingo/mem/agents/mem_writer_tools.py`（mem_* 工具沙箱、frontmatter 归一化、post-write hook 全部迁出或废弃）
  - `gateway.py` 删除 `_SearchClientProxy` / `search_client` 单例与 post-write hook 链路（MCP server 与 indexer 同进程，watcher 自动重索引）
  - system prompt 工具名一次性切到 MCP 名（`read`/`write`/`grep`/`find`/`ls`/`append`/`delete`），保留 `mem_gen_id`；增加 session.configure 自动设置说明
  - 新增 `pyproject.toml` 依赖 `langchain-mcp-adapters>=0.3.0`（官方适配，`MultiServerMCPClient` 异步上下文 + `load_mcp_tools`）
  - `tests/conftest.py` 新增 `tmp_mcp_workspace` / `mcp_inmem_server` 共用 fixture（in-memory FastMCP transport 替换 `mcp_vault_connection`）
  - 重写 `tests/test_mem_writer_agent.py`（32 用例）：ULID / events 路径 / system prompt（MCP 工具名） / writer 流程（per-entry ainvoke）/ lang 注入 / indexer 离线降级 / daemon 线程 / gateway 单例代理
  - 删 `tests/test_gateway_search_hook.py`（hook 链路消失）、`tests/test_mem_writer_search_integration.py`（post-write 路径已废）
  - 改动：`src/everlingo/mem/vault/mcp_server/mcp_server.py` ; `src/everlingo/mem/agents/mem_writer_agent.py` ; `src/everlingo/mem/agents/mem_writer_mcp_client.py` (新) ; `src/everlingo/gateway/gateway.py` ; `pyproject.toml` ; `tests/conftest.py` (新) ; `tests/test_mem_vault_mcp_server.py` ; `tests/test_mem_writer_agent.py` ; `docs/impl-spec/memory-writer-agent-spec.md`
- 2026-07-06 | `session.configure` 自动创建缺失的 lang vault：
  - `session.configure` 在 `lang` 不在 `workspace.lang_dirs()` 时内部调 `create_vault_tool` 自动创建 vault；创建失败（含非法 lang 名）返回 `isError=true` + `auto-create vault failed` 错误文案
  - `create_vault_tool` 的 invalid lang 名校验自然透传（`"a/b"` / `"."` / 空 / NUL 等）
  - `_SERVER_INSTRUCTIONS` 同步更新（点 3 文案）
  - spec 文档更新：`vault-mcp-spec.md`「lang 合法性」节、`vault-mcp-spec-tools.yaml` `session.configure.lang` description
  - 测试更新：`test_session_configure_invalid_lang` 改用非法名 `"a/b"`；新增 `test_session_configure_auto_creates_vault` / `test_session_configure_auto_create_failure_propagates`；`test_session_reconfigure_switches_lang` 去掉手动 `mkdir` 依赖自动创建
  - 改动：`src/everlingo/mem/vault/mcp_server/mcp_server.py` ; `docs/impl-spec/vault-mcp/vault-mcp-spec.md` ; `docs/impl-spec/vault-mcp/vault-mcp-spec-tools.yaml` ; `tests/test_mem_vault_mcp_server.py`
- 2026-07-06 | 修复 `mcp_vault_connection` 未检查 `session.configure` 返回 `isError` 的 Bug：
  - 根因：MCP `ClientSession.call_tool` 在服务端返回 `isError=True` 时不抛异常；`session.configure` 失败（如 `lang` 不在 `workspace.lang_dirs()`）时 `sess.lang` 未被设置但客户端继续 `load_mcp_tools` 并 yield tools；agent 调 `grep` 时服务端抛误导性 "session not configured: call session.configure first"，真实原因（"lang not found in workspace: xx"）丢失
  - 修复：configure 返回后检查 `isError`，失败抛 `IndexerOfflineError`（携带 `content[0].text`）。`mcp_vault_connection` 不再 yield tools，避免后续 `grep` 走到 `_require_session` 的失败分支
  - 调用方现有 `except IndexerOfflineError` 路径会 `logger.error` 记录真实原因并丢弃 entry
  - 改动：`src/everlingo/mem/agents/mem_writer_mcp_client.py`
