# Observability

## Logging
日志文件输出的默认路径： `$workspace/logs/everlingo.log` 。

日志的配置见 [configuration.md](/user-docs/reference/configuration.md)。 
日志的实现入口在 /src/everlingo/log_utils.py 。 

### logging level
本应用的日志分为 debug/info/warn/error 级别。
与 python logging 库的 mapping 关系：
```python
import logging
_LOG_LEVEL_MAP: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "error": logging.ERROR,
}
```

### Chat Agent 用户交互 IO 日志

用户消息输入与 Agent 回复文本的日志记录在 `Session` 层（`src/everlingo/gateway/session.py`），统一前缀 `[ChatAgent]`，level `debug`。
格式与字段说明见 [session.md — 交互日志](/docs/impl-spec/session.md#交互日志)。

### logging format

2026-06-28 15:42:25.123 [$logging_level] [$thread_id] [$thread_name] [$module] [$logger_name] : $message

### 进程与日志文件边界

本系统包含两个独立进程，各自写独立日志文件：

| 进程 | 入口 | 日志文件 | 主要日志内容 |
|------|------|----------|-------------|
| **everlingo gateway / CLI** | `src/everlingo/gateway/gateway.py:main` → `setup_logging()` | `$workspace/logs/everlingo.log` | gateway 运行日志、chat-agent tool 调用日志（logger `everlingo.tools`） |
| **indexer** | `src/everlingo/mem/vault/search/cli.py:cmd_indexer_start` → `_run_indexer` | `$workspace/logs/indexer.log` | indexer 运行日志、MCP Server 工具调用 debug 日志（logger `everlingo.mem.vault.mcp_server`，独立强制 DEBUG level） |

**MCP Server 工具调用日志归属 indexer.log**：因 MCP Server 部署拓扑为「内嵌于 indexer 进程的子线程」（见 [vault-mcp-spec.md](/docs/impl-spec/vault-mcp/vault-mcp-spec.md)「部署形态」），非 gateway/CLI 进程。MCP server 的 `everlingo.mem.vault.mcp_server` logger 在 indexer 进程的 uvicorn log_config 中独立配置，与 indexer 主日志同文件。gateway/CLI 不接收也不保存 MCP server 的日志记录。

## LLM Traffic Observability

### Langfuse 记录跟踪 LLM 流量

使用 Langfuse 记录跟踪 LLM 流量。

示例：
```python
from langfuse import get_client
from langfuse.langchain import CallbackHandler

# Initialize Langfuse client
langfuse = get_client()

# Initialize Langfuse CallbackHandler for Langchain (tracing)
langfuse_handler = CallbackHandler()
```