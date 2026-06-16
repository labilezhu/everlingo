# Agent 实现

Chatbot 中处理用户输入的消息，均应该使用 langchain 的 agent 去处理。

这里的 langchain 的 agent , 可由类似以下的代码来创建：
```python
from langchain.agents import create_agent

agent = create_agent("openai:gpt-5.5", tools=tools)
```

产品文档中的 `角色`，如 `词典老师` `翻译老师` 均由同一个 langchain agent 去实现。而不是不同的 Agent 。 

## 用户意图分析实现

用户意图的分析，应该交由 LLM / langchain agent 去判断，而不是代码实现。如 [product-spec.md](/docs/product/product-spec.md) 中的 `#### 用户意图分析`

```markdown
if 如果输入的用户消息以`目标学习语言`文本开始，且中间没有 `界面语言` 文字类文本：
  - 如果是一个词（英语的单词或中文的词）则判断用户意图为 `查单词`
  - 如果是多个词（英语的单词或中文的词）则判断用户意图为 `翻译`
else if 根据用户输入文本和上下文，智能判断为查询与修改配置，则调用工具执行。
else if 根据用户输入文本和上下文，智能判断为`查单词`或`翻译`
else if 根据用户输入文本和上下文，智能判断为`查单词`或`翻译`
else 提示用户意图未识别，给出一些可选的示例
```

## Agent tools

参考： [tools](/docs/impl-spec/tools.md)


