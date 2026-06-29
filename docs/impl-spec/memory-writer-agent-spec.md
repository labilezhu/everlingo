# Memory Writer Agent

负责写入 [memory vault](/docs/impl-spec/worksplace/memory-vault-spec.md) 。

不让 [Chat Agent](/docs/impl-spec/chat-agent-spec.md) 直接编辑 Markdown 文件。
Chat Agent 只输出结构化 Memory Ops，  Memory Writer Agent 负责验证、合并、写入文件。

Memory Writer Agent 用一个队列接收请求，然后**异步**处理。Memory Writer Agent 是全局单例和独立单线程或协程。由于使用独立单线程或协程，所以没有并发写文件问题。队列内容不需要持久化，可接受因程序非法结束的丢失。

即，用独立 daemon Thread + queue.Queue 。

单例归属：放 src/everlingo/gateway/gateway.py 模块级实例。

## sync conversation memory entries spec

Chat Agent 输出 sync conversation memory 请求 ， Memory Writer Agent 用一个队列接收请求，然后**异步**处理：
- 更新 Memory Vault

conversation memory entries 的格式示例：
```json
{
  "entries": [
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
      "mean_summary": "表示不明确、含糊、边界不清。日语中比中文“暧昧”使用范围更广。", // headword 的释义
      "conversation_context": "用户在学习日语小说《罗生门》时直接查词", // 在什么对话上下文中
    },
    {
      "chat_session_id": "",
      "entry_id": "", 
      "timestamp": "2026-11-21 15:58:56",
      "channel_name": "WechatChannel", 
      "item_type": "phrases",
      "why_want_to_save_memory": "推断用户需要记住",
      "user_intent": "translate", 
      "lang": "en",
      "interface_language": "zh-CN", // 界面语言
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

### 记录 events 的实现

events/ 的追加不该走 LLM。 

events_spec.md 是按日期 markdown 表格追加行，纯结构化追加。让 LLM 去 read→modify→write 当天 events 文件性价比很低，且增加幻觉/格式错误风险。所以：
- events/ 写入用代码直接 append（按日期拼路径，追加一行 markdown 表格行，文件不存在则创建带表头的文件）

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

### System prompt
System prompt 需要包括 src/everlingo/mem/vault/vault_spec.md ，因为需要告诉 Agent memory vault 的结构 。这个文件中有 `{{ include [参考 kb_items_spec.md](./kb_items_spec.md) }}` 的包含引用部分。使用 src/everlingo/utils/md_prompt_compiler.py 的  `PackageSource` 来处理 markdown 文件运行期合并问题。


### Agent tools
所有文件和目录操作，都只能使用相对 path。假设当前目录位于 $workspace/memory/ 目录。

工具沙箱：
mem_* 工具"只能用相对 path，假设当前目录位于 $workspace/memory/"。必须在工具层强制校验：解析后路径不能逃出 memory_dir()（防 ../）。否则 LLM 一次幻觉就写到 workspace 外。

- mem_create_tmp_file() 返回文件的相对 path。 文件放 `tmp/` 目录下，文件名 pattern 为： tmp_$(uuid).md
- mem_read_file(path)	读取文件。返回文本文件内容。`tmp/` 目录下可以放
- mem_write_file(path, content)	覆盖写入或新建文件 。返回写入结果
- mem_append_file(path, content)	追加写入或新建文件 。返回写入结果
- mem_remove_file(path)	删除文件 。返回写入结果
- mem_list_directory(path)	列出指定目录下的文件或目录。返回格式： `[{file_name:"", size_bytes:128, create_time: "2025-12-24 22:21:00", modify_time: "2025-12-24 22:21:00" }]`
- mem_search_files(path, pattern)	按文件名搜索，目录递归。pattern 的格式与 Linux find 命令的 "-name pattern" 类似，支持 "*"。返回格式： `[{file_path:"", is_dir: false}]` , 输出的 file_path 为输入 path 的相对路径。
- mem_grep(path, pattern)	按内容正则搜索，目录递归。返回格式： `[{file_path:"",matched_text:""}]`, 输出的 file_path 为输入 path 的相对路径。
- mem_gen_id() 返回类似 01JZABD123 格式的 随机 id。 可用于 markdown 文件名部分。
