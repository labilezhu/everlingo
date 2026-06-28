
我准备为项目加入知识点记忆功能。直接让 LLM Agent 读写 memory markdown 文件。设计文档见 docs/impl-spec/chat-agent-spec.md 中的 “### memory writer agent 同步筛选” 一节 与 docs/impl-spec/memory-writer-agent-spec.md。 

实现分几个阶段，现在阶段主要是内部测试用，看实现可行性：
- 先不使用全文搜索和语义搜索。
- 用户知识知识可能会被记忆，但不直接或间接访问记忆的内容
- 记忆只写不读，不搜索

请你就这个设计，在产品层面，以及实现设计层面，说说你的意见。


---



我准备为项目加入知识点记忆功能。现开发一个可行性测试版本，我将自己运行试用，通过观察日志，作一个可行性测试。
- 先实现记忆筛选[Memory Extract Agent](docs/impl-spec/memory-extract-agent-spec.md)功能。
- 暂不实现 [Memory Writer Agent](docs/impl-spec/memory-writer-agent-spec.md)

你计划一下。


---

现在的 [Chat Agent](/docs/impl-spec/chat-agent-spec.md) 异步给对话内容给 [Memory Extract Agent](/docs/impl-spec/memory-extract-agent-spec.md) 去筛选记忆。 但这个设计让 Chat Agent 无法很好地知道记忆筛选结果，就无法向用户提供有用的记忆反馈。 我想修改成同步的调用，这样 Chat Agent 就知识记忆情况，可以更有信心地和用户沟通了。你觉得如何？分析一下，包括从产品设计和实现架构两方面说说。

---

太复杂了，我还是觉得，为 Chat Agent 提供一个 tool ，查询一下最近的 Memory Extract Agent 的输出结果就好。在用户需要落实询问记忆保存时，才查询，你觉得怎样？


--- 

现在 [Memory Extract Agent](/docs/impl-spec/memory-extract-agent-spec.md) 的去重方法是 headwords 。但 headwords 就算是同一个 session 的相同 message history 片段，其实每次都不同。如：

```markdown
1. 用户输入消息：I goes to school

2. Chat Agent 返回消息：
````markdown
你写的 **"I goes to school"** 有一个语法小问题哦～ 问题出在动词 **goes** 上。

**问题分析：**
- 主语 **I**（第一人称单数）后面应该跟动词原形，而不是 **goes**
- **goes** 是第三人称单数（he/she/it）用的形式

**正确说法：**
> **I go to school.**
````

3. Memory Extract Agent: 筛选出记忆
````log
channel_name=StdioChannel item_type=grammar why=纠正事项 user_intent=None lang=en headword=I go to school mean_summary='主语为第一人称单数 I 时，动词应使用原形，而非第三人称单数形式 goes。' conversation_context="用户写了 'I goes to school'，AI 纠正为 'I go to school'，并解释主谓一致规则。"
````
```

然后，用户在同一个 session 继续聊天：
```markdown
1. 用户输入消息：Hi
2. Chat Agent 返回消息：Hello

Memory Extract Agent: 筛选出记忆
````log
3. channel_name=StdioChannel item_type=grammar why=纠正事项 user_intent=None lang=en headword=go mean_summary='主语为第一人称单数 I 时，动词应使用原形，而非第三人称单数形式 goes。' conversation_context="用户写了 'I goes to school'，AI 纠正为 'I go to school'，并解释主谓一致规则。"
````
```

可见，有两个问题：
- 同一个历史消息被 extract 了两次
- 同一个历史消息被 extract 了两次，而且两次的 headword 不同。就算现在  LLM 的 temperature=0 了

我的问题是：
- 同一个历史能不 extract 两次吗？