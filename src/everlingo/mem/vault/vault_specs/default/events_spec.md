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
        2027-08-26.md
```

## markdown 文件示例

文件前置内容：

```markdown
# 当天事件

事件按时间顺序记录，即最早的事件在前面。
事件记录格式： 

```

每个 event 增加一个 markdown 段落，如：

```markdown
## Event
- chat_session_id: 49c  
- entry_id: 6b9  
- timestamp: 2026-11-21 14:58:56  
- channel_name: WechatChannel  
- item_type: vocab  
- why_want_to_save_memory: 用户明确要求记住知识点  
- user_intent: dict  
- lang: ja  
- title: 曖昧  

### conversation_context
用户在学习日语小说《罗生门》时直接查词  

```


