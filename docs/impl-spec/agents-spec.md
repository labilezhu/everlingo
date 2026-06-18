# Agent 实现

应实现于： `/src/everlingo/agents/agent.py` ，主要实现在 `class MainAgent` 。


Chatbot 中处理用户输入的消息，均应该使用 langchain 的 agent 去处理。

这里的 langchain 的 agent , 可由类似以下的代码来创建：
```python
from langchain.agents import create_agent

agent = create_agent("openai:gpt-5.5", tools=tools)
```

产品文档中的 `角色`，如 `词典老师` `翻译老师` 均由同一个 langchain agent 去实现。而不是不同的 Agent 。 


## 用户意图分析、执行、回复响应
`用户意图的分析`，应该交由 LLM / langchain agent 去判断，而不是代码实现。

Agent 的`用户意图分析` 与 `用户意图的执行与回复响应` 见 Agent 的 system prompt:

`src/everlingo/agents/agent.py` 中的 `_build_system_prompt()`

由于 Agent 可能会动态修改 `配置` 和 `用户Profile`。 而 `_build_system_prompt()` 又依赖于这些配置，所以次轮对话，即每次 `agent.invoke()` 前，都需要刷新一下 system prompt 。

### system prompt 维护

system prompt 刷新:

由于 system prompt 使用了 User Profile 。 而用户可能动态修改 user profile 。所以 system prompt 也要刷新。
实现思路：`conf_manager.py` 维护模块级 `_config_version` 计数器，`set_config` 工具每次成功写入后递增；`MainAgent.__init__()` 记录当时的版本号，每次 `invoke()` 前调用 `_refresh_agent_if_needed()`，发现版本号变化时用 `load_profile()` 重新构建 system prompt 并 `create_agent()`，版本号同步后不再重建

## Agent tools

参考： [tools](/docs/impl-spec/tools.md)


## Observability
所有发给 LLM 的请求都写入日志文件。见 [observability.md](/docs/impl-spec/observability.md) 。 日志 level 是 debug 。


