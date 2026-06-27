# Observability

## Logging
日志文件输出的默认路径： `$workspace/logs/everlingo.log` 。

日志的配置见 [configuration.md](/user-docs/reference/configuration.md)。 
日志的实现入口在 /src/everlingo/logging.py 。 

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