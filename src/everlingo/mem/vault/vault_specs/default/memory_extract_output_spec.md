# Memory Extract Output Spec

 Memory Extract 输出为一个 json 数组：
```json
[{//Memory Entry
}]
```

## 记忆实体(Memory Entry) 结构说明


```json
{
  "chat_session_id": "", // 会话 id
  "entry_id": "", // 新生成 uuid
  "timestamp": "2026-11-21 14:58:56", //yyyymmdd HH:mm:ss
  "channel_name": "WechatChannel", //session 相关的 channel name
  "user_intent": "dict", // 用户在 chatbot 上的意图： None=其它, "dict"=查词, "translate"=翻译
  "lang": "ja", 
  "interface_language": "zh-CN",
  "why_want_to_save_memory": "用户明确要求记住知识点", 
  "item_type": "vocab", 
  "title": "曖昧", 
  "new_messages": "",
  "context_messages": "",
}
```

### 字段说明

- lang: 目标学习语言
- interface_language: 界面语言
- why_want_to_save_memory ： 为什么要记住。 用户明确要求记住知识点 / 纠正事项。
- item_type ： 记忆类型。 vocab （单词）/ phrase （短语）/ grammar （语法点）/ pragmatics （语用） / others 。
- title: 主要使用`界面语言`，限一句话，描述本`知识点`。用于语义搜索和 full text search。 
- new_messages ：触发记忆的对话消息。
- context_messages ：最近的历史对话。

