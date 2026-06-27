# Memory Writer Agent

负责写入 [memory vault](/docs/impl-spec/worksplace/memory-vault-spec.md) 。

不让 [Chat Agent](/docs/impl-spec/chat-agent-spec.md) 直接编辑 Markdown 文件。
Chat Agent 只输出结构化 Memory Ops，  Memory Writer Agent 负责验证、合并、写入文件。


## Memory Ops

Chat Agent 输出 Memory Ops 请求 ， Memory Writer Agent 接收并分析和执行。 

Memory Ops 的格式示例：
```json
{
  "ops": [
    {
      "type": "upsert_item",
      "item_type": "vocab",
      "lang": "ja",
      "headword": "曖昧",
      "reading": "あいまい",
      "aliases": ["あいまい", "ambiguous"],
      "tags": ["ja", "vocab", "confusing"],
      "summary": "表示不明确、含糊、边界不清。日语中比中文“暧昧”使用范围更广。",
      "source_context_id": "01JZCTX123"
    },
    {
      "type": "increment_seen_count",
      "target": "曖昧",
      "lang": "ja"
    },
    {
      "type": "create_review_card",
      "target": "曖昧",
      "card_type": "recognition"
    }
  ]
}
```

## 处理 Memory Ops

1. 查找是否已有词条；
2. 判断是否合并；
3. 更新 frontmatter；
4. 追加 encounter log；

每步都需要有 info 级别的日志输出，描述写了什么，什么内容。

## 实现
应实现于： `/src/everlingo/mem/agents/mem_writer_agent.py`。

用 langchain 的 agent 框架。有自己的 system prompt 。
