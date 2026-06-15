# Agent 实现

所有的代码中，所有的 LLM 交互，均应该使用 langchain 的 agents 封装。

如：
```python
from langchain.agents import create_agent

agent = create_agent("openai:gpt-5.5", tools=tools)
```

## Agent tools

参考： [tools](/docs/impl-spec/tools.md)