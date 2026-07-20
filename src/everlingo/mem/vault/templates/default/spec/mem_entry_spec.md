# 记忆实体(Memory Entry) 结构说明

```json
{
  "operation": "create", // "create"(默认) | "delete" | "edit"
  "chat_session_id": "", // 会话 id
  "entry_id": "", // 新生成 uuid
  "timestamp": "2026-11-21 14:58:56", //yyyymmdd HH:mm:ss
  "channel_name": "WechatChannel", //session 相关的 channel name
  "lang": "ja", 
  "interface_language": "zh-CN",
  "why_want_to_save_memory": "用户明确要求记住知识点", 
  "item_type": "vocab", 
  "title": "曖昧", 
  "new_messages": "",
  "context_messages": "",
  "file_path": null, // delete/edit 必选：相对 vault 根的文件路径
  "body": null,      // edit 必选：新 markdown 正文（不含 frontmatter）
}
```

## 字段说明

- operation: 操作类型。 `"create"`（默认，新建/合并条目） / `"delete"`（删除笔记文件） / `"edit"`（编辑笔记正文）。不填此字段即默认为 create。 
- lang: 目标学习语言
- interface_language: 界面语言
- why_want_to_save_memory ： 为什么要记住。 用户明确要求记住知识点 / 纠正事项 / Chat Agent 判定。
- item_type ： 记忆类型/`知识点类型`。 vocab （单词）/ phrase （短语）/ grammar （语法点）/ pragmatics （语用） / others 。
- title: 主要使用`界面语言`，限一句话，描述本`知识点`。用于语义搜索和 full text search。delete/edit 时 entry 的 title 仅为占位。
- new_messages ：触发记忆的对话消息。delete/edit 操作忽略此字段。
- context_messages ：最近的历史对话。delete/edit 操作忽略此字段。
- file_path: delete/edit 操作必选。相对 vault 根的文件路径，如 `"items/vocab/aimai--01JZABD123.md"`。create 操作忽略此字段。
- body: edit 操作必选。新的 markdown 正文内容（不含 frontmatter YAML 元数据段）。delete 与 create 操作忽略此字段。

