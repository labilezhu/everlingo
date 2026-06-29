# 事件类

事件记忆，也就是“什么时候，在什么场景和上下文中，学了什么知识点”。

用途：

- 保留学习场景；
- 支持回溯；
- 支持“你上次问过这个词”；
- 支持生成学习周报。

目录结构：
```
    2026/ #年
      06/ #月
        2026-06-26.md #文件名按这个格式
    2027/
      08/
        2026-06-26.md
```

按

## markdown 文件示例


```markdown
# 当天事件

事件按时间顺序记录，即最早的事件在前面。
事件记录格式： 

| chat_session_id | entry_id | timestamp | channel_name | item_type | why_want_to_save_memory | user_intent | lang | headword | mean_summary | conversation_context |
|---|---|---|---|---|---|---|---|---|---|---|
| 49c | 6b9 | 2026-11-21 14:58:56 | WechatChannel | vocab | 用户明确要求记住知识点 | dict | ja | 曖昧 | 表示不明确、含糊、边界不清。日语中比中文“暧昧”使用范围更广。 | 用户在学习日语小说《罗生门》时直接查词 |
| 93b | 3d4 | 2026-11-21 15:58:56 | WechatChannel | phrases | 推断用户需要记住 | translate | en | take for granted | 认为是理所当然的 | 用户翻译一封来自 manager 的 email 内容 |
```


