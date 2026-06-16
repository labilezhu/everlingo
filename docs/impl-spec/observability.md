# Observability

## Logging
日志文件输出的默认路径： `~/.everlingo/logs/everlingo.log` 。

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