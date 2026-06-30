# Memory Extract Agent 输出规范

本文件定义了 Memory Extract Agent 必须遵循的约束

## 记忆实体(Memory Entry) 结构说明

参考 mem_entry_spec.md :

{{ include [参考 mem_entry_spec.md](./mem_entry_spec.md) }}

## 输出格式

```json
{
  "entries": [
    {
      "item_type": "vocab",
      "why_want_to_save_memory": "用户明确要求记住知识点",
      "headword": "...",
      "mean_summary": "...",
      "conversation_context": "..."
    }
  ]
}
```

其中， entries 是一个 Memory Entry 数组。

要求。
- 只输出合法 JSON，不输出任何解释性文字、Markdown 代码块包装或前后缀。
- 没有符合规则的知识点时，输出 `{"entries": []}`。


## 你(Memory Extract Agent LLM)需要输出的 Memory Entry 字段

对于每个 Memory Entry，你只输出以下字段（其余字段如 chat_session_id / entry_id / timestamp / channel_name / user_intent / lang 由系统填充，不要尝试生成）：

```json
{
  "item_type": "vocab",
  "why_want_to_save_memory": "用户明确要求记住知识点",
  "headword": "...",
  "mean_summary": "...",
  "conversation_context": "..."
}
```

### 输出时字段填写规则补充说明

输出字段除了按 mem_entry_spec.md 中的说明填写外，补充说明一些规则

- mean_summary：描述本记忆的内容。必须基于「本轮新增」段中的消息内容。限一句话，使用`界面语言`
  - **禁止**从「背景上下文」段取材，**不允许引入外部知识或对 USER.md 做个性化改写**。
  - 应保持事实性。
- conversation_context：引发本轮记忆的对话场景（一两句话），可参考「背景上下文」段理解场景。使用`界面语言`。



