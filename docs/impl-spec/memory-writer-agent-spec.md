# Memory Writer Agent

负责写入 [memory vault](/docs/impl-spec/worksplace/memory-vault-spec.md) 。

Memory Writer Agent 负责验证、合并 [Memory Extract Agent](/docs/impl-spec/memory-extract-agent-spec.md) 的输出，并写入 memory vault 。

Memory Writer Agent 用一个队列接收请求，然后**异步**处理。Memory Writer Agent 是全局单例和独立单线程或协程。由于使用独立单线程或协程，所以没有并发写文件问题。队列内容不需要持久化，可接受因程序非法结束的丢失。

即，用独立 daemon Thread + queue.Queue 。

单例归属：放 src/everlingo/gateway/gateway.py 模块级实例。


## 输入
见： [Memory Entry 结构说明](/src/everlingo/mem/agents/mem_entry_spec.md) 。

Memory Extract Agent 转交每条 entry 时会填充 `chat_session_id` / `entry_id` / `timestamp` / `channel_name` / `user_intent` / `lang` / `interface_language` 等系统字段；Writer Agent 不应自行生成或改写这些字段。


## 处理 Memory Entry

写入 [memory vault](/docs/impl-spec/worksplace/memory-vault-spec.md)
1. 记录 [events](/src/everlingo/mem/vault/events_spec.md) 。
2. 更新 知识点类 memory items

日志要求：每次写文件，都需要有 info 级别的日志输出，描述写了什么文件，什么内容。

### 记录 events 的实现

events/ 的追加不该走 LLM。 

 events_spec.md 是按日期 markdown 文件追加，纯结构化追加。让 LLM 去 read→modify→write 当天 events 文件性价比很低，且增加幻觉/格式错误风险。所以：
- events/ 写入用代码直接 append markdown 段落（按日期拼路径，追加内容，文件不存在则创建带 前置内容的 markdown 文件）

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

System prompt 还需要包括 src/everlingo/mem/agents/mem_entry_spec.md ，用于告知 Agent 其输入 entry 的完整字段结构与字段含义（字段补充说明）。同样通过 `PackageSource` + `compile_prompt` 加载。

注入 `mem_entry_spec.md` 与 `vault_spec.md` 前，需用 `md_prompt_compiler.shift_headings(doc, 2)` 整体平移标题 +2 级，使其最浅标题 h1 → h3，嵌套于外层 `## 输入 entry 结构` / `## memory vault 结构` (h2) 之下。此约定与 `chat-agent-spec.md` 中「*.md 注入需降级标题」一致。`compile_prompt` 内部的 `context_level` 机制只调整 include 子文件标题，不调整入口文件自身标题，故需 `shift_headings` 在编译输出上额外平移。

另外，system prompt 需包含一段「语言配置」说明，明确告诉 Agent 两个语言字段的来源与用途：

- `目标学习语言`：来自 entry 的 `lang` 字段（语言代码，如 `ja`、`en`），表示用户正在学习的语言。kb item 中对该语言的引用（headword、词形、例句）必须使用该语言本身书写。
- `界面语言`：来自 entry 的 `interface_language` 字段（语言代码，如 `zh-CN`），表示用户界面使用的语言。memory vault 中 markdown 文件正文（释义、记忆钩子、conversation_context 等）必须主要使用界面语言编写。

两个字段值由 Memory Extract Agent 在上游填充，Writer Agent 直接采用，不要自行推断或改写。


### Agent tools
所有文件和目录操作，都只能使用相对 path。假设当前目录位于 `$workspace/memory/languages/$lang/vault/` 目录（`$lang` 为 entry 的 `lang` 字段对应的目标学习语言目录）。工具层按当前会话的 `lang` 解析到对应语言的 vault 根。

工具沙箱：
mem_* 工具"只能用相对 path，假设当前目录位于 `$workspace/memory/languages/$lang/vault/`"。必须在工具层强制校验：解析后路径不能逃出该 lang 的 vault_dir()（防 ../）。否则 LLM 一次幻觉就写到 vault 外。

- mem_create_tmp_file() 返回文件的相对 path。 文件放 `tmp/` 目录下，文件名 pattern 为： tmp_$(uuid).md
- mem_read_file(path)	读取文件。返回文本文件内容。`tmp/` 目录下可以放
- mem_write_file(path, content)	覆盖写入或新建文件 。返回写入结果
- mem_append_file(path, content)	追加写入或新建文件 。返回写入结果
- mem_remove_file(path)	删除文件 。返回写入结果
- mem_list_directory(path)	列出指定目录下的文件或目录。返回格式： `[{file_name:"", size_bytes:128, create_time: "2025-12-24 22:21:00", modify_time: "2025-12-24 22:21:00" }]`
- mem_search_files(path, pattern)	按文件名搜索，目录递归。pattern 的格式与 Linux find 命令的 "-name pattern" 类似，支持 "*"。返回格式： `[{file_path:"", is_dir: false}]` , 输出的 file_path 为输入 path 的相对路径。
- mem_grep(path, pattern)	按内容正则搜索，目录递归。返回格式： `[{file_path:"",matched_text:""}]`, 输出的 file_path 为输入 path 的相对路径。
- mem_gen_id() 返回类似 01JZABD123 格式的 随机 id。 可用于 markdown 文件名部分。
