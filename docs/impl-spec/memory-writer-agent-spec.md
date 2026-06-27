# Memory Writer Agent

负责写入 [memory vault](/docs/impl-spec/worksplace/memory-vault-spec.md) 。

不让 [Chat Agent](/docs/impl-spec/chat-agent-spec.md) 直接编辑 Markdown 文件。
Chat Agent 只输出结构化 Memory Ops，  Memory Writer Agent 负责验证、合并、写入文件。


## sync conversation memory entries spec

Chat Agent 输出 sync conversation memory 请求 ， Memory Writer Agent 用一个队列接收请求，然后**异步**处理：
- 分析什么需要更新到 Memory Vault ，什么不需要。 
- 更新 Memory Vault

conversation memory entries 的格式示例：
```json
{
  "entries": [
    {
      "item_type": "vocab", // 知识类型： vocab / phrases / grammar / pragmatics
      "why_want_to_save_memory": "用户显式要求记住", //为什么 chatbot 深度保存记忆： 触发真实记忆的可能性由高到低分为： 用户显式要求记住 / 推断用户需要记住 / 记录用户对话
      "user_intent": "dict", // 用户在 chatbot 上的意图： None=其它, "dict"=查词, "translate"=翻译
      "lang": "ja", // 目标学习语言
      "headword": "曖昧", // 知识的 keyword : 单词时为单词本身。 短语就如： 
      "mean_summary": "表示不明确、含糊、边界不清。日语中比中文“暧昧”使用范围更广。", // headword 的释义
      "conversation_context": "用户在学习日语小说《罗生门》时直接查词", // 在什么对话上下文中
    },
    {
      "user_intent": "translate", 
      "item_type": "phrases",
      "lang": "en",
      "headword": "take for granted",
      "mean_summary": "认为是理所当然的",
      "conversation_context": "用户翻译一封来自 manager 的 email 内容", // 在什么对话上下文中
    }
  ]
}
```

## 处理 conversation memory entries

写入 [memory vault](/docs/impl-spec/worksplace/memory-vault-spec.md)
1. 记录 [events](/src/everlingo/mem/vault/events_spec.md) 。
2. 更新 知识点类 memory items

日志要求：每次写文件，都需要有 info 级别的日志输出，描述写了什么文件，什么内容。

### 更新 知识点类 memory items

1. 根据 `目标学习语言` / 知识类型 / 查找 memory vault 中是否已记录。可以找类似 grep 命令的方法找文件内容关键字。
2. 如已记录则合并，如未记录则创建 ；
3. 更新知识点 markdown 文件。对于目标  markdown 文件，llm 只调用一次 `read_file` 工具，llm 只调用一次 `write_file`  工具。
   1. 追加 `遇到记录`；
   2. 更新 frontmatter ；
   3. 根据 [kb_items_spec.md](/src/everlingo/mem/vault/kb_items_spec.md) 对应 知识类型 的正文格式和段落要求，更新 markdown 文件正文内容

## 实现
应实现于： `/src/everlingo/mem/agents/mem_writer_agent.py`。

用 langchain 的 agent 框架。有自己的 system prompt 。

### Agent tools
所有文件和目录操作，都只能使用相对 path。假设当前目录位于 $workspace/memory/ 目录。

- mem_read_file(path)	读取文件。返回文本文件内容
- mem_write_file(path, content)	覆盖写入或新建文件 。返回写入结果
- mem_list_directory(path)	列出指定目录下的文件或目录。返回格式： `[{file_name:"", size_bytes:128, create_time: "2025-12-24 22:21:00", modify_time: "2025-12-24 22:21:00" }]`
- mem_search_files(path, pattern)	按文件名搜索，目录递归。pattern 的格式与 Linux find 命令的 "-name pattern" 类似，支持 "*"。返回格式： `[{file_path:"", is_dir: false}]`
- mem_grep(pattern, path)	按内容正则搜索，目录递归。返回格式： `[{file_path:"",matched_text:""}]`
