

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

---

实现 [Memory Writer Agent](docs/impl-spec/memory-writer-agent-spec.md)，并让 [Memory Extract Agent](/docs/impl-spec/memory-extract-agent-spec.md) 的输出写入 Memory Writer Agent。


--- 

由于 src/everlingo/mem/vault/vault_spec.md 中的 markdown 文件使用的主语言需要指定为应用配置的 `界面语言`。：
- vault_spec.md  新增加了一节 “## Markdown 文件使用什么语言编写”
- docs/impl-spec/memory-writer-agent-spec.md 中 “## sync conversation memory entries spec” 加入了 “"interface_language": "zh-CN", // 界面语言” 字段。
- src/everlingo/mem/agents/mem_writer_agent.py 的 system prompt 需要同步这个变更


---

docs/impl-spec/memory-writer-agent-spec.md 的 “### 记录 events 的实现” 一节设计有变化
以前的设计是：
```
events/ 的追加不该走 LLM。 

 events_spec.md 是按日期 markdown 表格追加行，纯结构化追加。让 LLM 去 read→modify→write 当天 events 文件性价比很低，且增加幻觉/格式错误风险。所以：
- events/ 写入用代码直接 append（按日期拼路径，追加一行 markdown 表格行，文件不存在则创建带表头的文件）
```
请更新代码，以实现当前设计


---

/src/everlingo/mem/agents/mem_extract_agent.py 需要把现在代码中有关 “输出 schema” 与 “输出字段说明与真实性约束” 部分的 system prompt ，移动到 /src/everlingo/mem/agents/mem_extract_spec.md 中。
然后加载 prompt 的方式，修改成与 src/everlingo/mem/agents/mem_writer_agent.py 加载 /src/everlingo/mem/vault/vault_spec.md 到 system prompt 的方式一致（运用 compile_prompt 与 PackageSource ） 。

