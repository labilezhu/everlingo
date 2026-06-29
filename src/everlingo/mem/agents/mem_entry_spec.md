# 记忆实体(Memory Entry) 结构说明

```json
{
  "chat_session_id": "", // 会话 id
  "entry_id": "", // 新生成 uuid
  "timestamp": "2026-11-21 14:58:56", //yyyymmdd HH:mm:ss
  "channel_name": "WechatChannel", //session 相关的 channel name
  "item_type": "vocab", // 知识类型： vocab / phrases / grammar / pragmatics
  "why_want_to_save_memory": "用户明确要求记住知识点", //为什么 chatbot 深度保存记忆： 触发真实记忆的可能性由高到低分为： 用户明确要求记住知识点 / 纠正事项 / 推断用户需要记住
  "user_intent": "dict", // 用户在 chatbot 上的意图： None=其它, "dict"=查词, "translate"=翻译
  "lang": "ja", // 目标学习语言
  "interface_language": "zh-CN", // 界面语言
  "headword": "曖昧", // 知识的 keyword : 单词时为单词本身。 短语就如： 
  "mean_summary": "表示不明确、含糊、边界不清，日语中比中文“暧昧”使用范围更广。", // headword 的释义
  "conversation_context": "用户在学习日语小说《罗生门》时直接查词", // 在什么对话上下文中
}
```

## 字段补充说明

- **item_type**： 记忆类型。 vocab （单词）/ phrases （短语）/ grammar （语法点）/ pragmatics （语用） / others。
- **why_want_to_save_memory**： 为什么要记住。 用户明确要求记住知识点 / 纠正事项。
- **headword**：在相同的 item_type 下，标识这个记忆的关键文本，最多一句话，保持简洁。 根据 item_type 的不同有不同取值倾向：
  - vocab 时为单词本身
  - phrases 则为短语本身
  - grammar 为语法点名称，用 `界面语言` 表达
  - pragmatics 为语用的关键单词
  - other 为能标识这个记忆的关键字，使用的语言由你判断
- **mean_summary**：描述本记忆的内容。限一句话，使用`界面语言`
- **conversation_context**：引发本轮记忆的对话场景（一两句话）。使用`界面语言`。