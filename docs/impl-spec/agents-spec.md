# Agent 实现

Chatbot 中处理用户输入的消息，均应该使用 langchain 的 agent 去处理。

这里的 langchain 的 agent , 可由类似以下的代码来创建：
```python
from langchain.agents import create_agent

agent = create_agent("openai:gpt-5.5", tools=tools)
```

产品文档中的 `角色`，如 `词典老师` `翻译老师` 均由同一个 langchain agent 去实现。而不是不同的 Agent 。 

## 用户意图分析

用户意图的分析，应该交由 LLM / langchain agent 去判断，而不是代码实现。

实现参考 [/docs/product/pro-chatbot.md]

主要的 Agent System Prompt 位于： /src/everlingo/chat.py 中的 `_build_system_prompt`


## 用户意思的执行与回复响应
参考 [/docs/product/pro-chatbot.md] 中 `## 用户意图响应`


## Agent tools

参考： [tools](/docs/impl-spec/tools.md)


## Observability
所有发给 LLM 的请求都写入日志文件。见 [observability.md](/docs/impl-spec/observability.md) 。 日志 level 是 debug 。


