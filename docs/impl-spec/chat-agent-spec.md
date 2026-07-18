# Chat Agent

应实现于： `/src/everlingo/agents/agent.py` ，主要实现在 `class MainAgent` 。


Chatbot 中处理用户输入的消息，均应该使用 langchain 的 agent 去处理。

这里的 langchain 的 agent , 可由类似以下的代码来创建：
```python
from langchain.agents import create_agent

agent = create_agent("openai:gpt-5.5", tools=tools)
```

## 用户意图分析、执行、回复响应
`用户意图的分析`，应该交由 LLM / langchain agent 去判断，而不是代码实现。

`用户意图类型` 按识别优先级从高到低分为（与 system prompt `agent.py` 中 `_build_system_prompt()` 一致）：
1. 查单词
2. 翻译
3. 语言学习问题智能问答
4. 管理 USER.md
5. 管理基本配置
6. 未识别输入
7. 笔记读取和浏览
8. 抽取对话内容到笔记
9. 笔记删除
10. 笔记编辑

其中 #8 走异步 `request_memory_extraction` 工具（见下文「Memory Extract」节）；#9 / #10 走同步 `memory_writer_action` 工具（见下文「笔记删除与编辑」节）。

Agent 的`用户意图分析` 与 `用户意图的执行与回复响应` 见 Agent 的 system prompt:
`src/everlingo/agents/agent.py` 中的 `_build_system_prompt()`

### invoke -> ainvoke

`MainAgent.invoke` 为 async 方法 `ainvoke`，因为 MCP 工具（vault 只读）需要异步 session。
`Session.run` 用 `await self.agent.ainvoke(...)` 调用。



## system prompt 构造

### system prompt 刷新

由于 system prompt 使用了 User Profile 与 用户自由偏好笔记 (USER.md) 。而用户/Agent 可能动态修改它们。所以 system prompt 也要刷新。

实现思路：
- `setting.py` 维护模块级 `_prompt_version` 计数器；`conf_manager.set_config` 与 `user_doc.user_doc_set` 每次成功写入后调用 `bump_prompt_version()` 递增。
- `MainAgent.__init__()` 记录当时的版本号与 `prompt_input_mtime()`（`everlingo.yaml` 与 `USER.md` 的最新 mtime）；每次 `invoke()` 前调用 `_refresh_agent_if_needed()`，发现**版本号变化**或**任一依赖文件 mtime 变化**时，用 `load_profile()` + `load_user_doc()` 重新构建 system prompt 并 `create_agent()`，同步后不再重建。
- mtime 检测使外部编辑器修改 `everlingo.yaml` / `USER.md` 也能即时生效。

### 注入 *.md 文件时标题层级处理
*.md 文件内容注入到 prompt 时，其中所有 markdown 标题需要根据注入目标位置的 markdown 标题级数，进行降级，防止用户自由文本中的标题与 prompt 外层结构冲突。
如注入目标是 "##" 的，注入的 markdown 文本标题要增加两个级数。

参考实现见 `agent.py` 中的 `_demote_headings()` 函数。

### 注入 USER.md 
`USER.md` 内容注入到 `## 用户自由偏好笔记 (USER.md)` 节。
结构说明见 [USER-spec.md](/docs/impl-spec/worksplace/USER-spec.md)

### 注入 Channel 能力与注意事项

`ChannelMetadata.channel_prompt` 内容注入到 `## 当前对话通道 (Channel) 能力与注意事项` 节。
使 Agent 了解当前通道的特性、限制和支持的能力。

### 分级语音 prompt 注入

根据 `ChannelMetadata.supported_sound_media_format` 是否包含 `"mp3"`，注入不同的语音相关 prompt：

**支持 mp3 时**：
- 注入 `## 语音发送能力` 节，说明何时调用 `voice_speak` 工具
- 提供 `voice_speak` 工具（见 [chat-agent-tools-spec.md](/docs/impl-spec/chat-agent-tools-spec.md)）

**不支持 mp3 时**：
- 注入 `## 语音发送能力` 节，告知 Agent 当前通道不支持语音
- 若用户要求发送语音，Agent 应文字回复「当前通道不支持语音，请在微信等支持语音的通道使用。」


## 多消息回复

`MainAgent.invoke()` 返回 `list[MessageEvent]`，每条对应一个消息气泡（微信、stdio 等通道每次 `send` 为一条独立消息）。

LLM 的工具调用循环可能产生多个 `AIMessage`。例如「翻译并朗读 ufo」：
```
AIMessage(content="UFO — 不明飞行物…", tool_calls=[voice_speak(...)])  # 含正文 + 工具调用
ToolMessage(content="voice scheduled")                                  # 工具结果
AIMessage(content="")                                                   # 最终空消息
```

回复聚合规则：
- 每个**非空 `AIMessage.content`** 作为一个独立的 `MessageEvent`，按出现顺序加入返回列表
- 跳过 `ToolMessage`（其 content 如 `"voice scheduled"` 是工具结果，不给用户；语音已由 `voice_speak` 异步直发 channel）
- 本轮无非空 `AIMessage`（如 LLM 只调了工具无文字）→ 返回 `[]`（不发消息，语音已由工具直发）
- 异常路径 → 返回单元素列表 `[MessageEvent(...)]`

`Session.run()` 对返回列表逐条调用 `channel.send()`，形成多个消息气泡。

## Memory Vault 只读访问

Chat Agent 可以查询用户的记忆库（Memory Vault）以提供更准确的回复。实现方案：

- **MCP 长连接**：MainAgent 维护一条到 Vault MCP Server 的长连接 Stream（`mcp_vault_connection`），在 `__init__` 后首次 `ainvoke` 时懒加载打开。
- **lang 自动绑定**：`session.configure(lang=profile.target_language)`，与 Chat Agent 当前 `target_language` 一致；配置变更时重建 agent 并重开 stream。
- **只读工具子集**：Chat Agent 只加载 5 个只读工具：
  - `vault_mcp_search`, `vault_mcp_read`, `vault_mcp_ls`, `vault_mcp_find`, `vault_mcp_grep`
- **运行时学习 vault 结构**：System prompt 只注入简短说明，不写 VAULT_SPEC.md 全文。LLM 在需要时通过 `vault_mcp_read(path="VAULT_SPEC.md")` 了解 vault 结构规范。
- **离线圈降级**：Indexer 离线（MCP 连不上）时 Chat Agent 仍可正常回复，只是没有 vault 工具。system prompt 注入「记忆库暂不可用」提示。

### system prompt 注入

system prompt 新增简短一节（仅 vault 在线时）：

```
## 记忆库只读访问
当用户明显要查询过往笔记/记忆时（如「我记过 xxx 吗」「查我笔记」），可使用 vault 工具。
不了解 vault 结构时先 vault_mcp_read(path="VAULT_SPEC.md") 学习规范。
你只读不写；需要写入时通过 `request_memory_extraction` 工具触发异步抽取流程。
```

vault 离线时改为：
```
## 记忆库访问
记忆库暂不可用，请告知用户稍后再试。
```

## Memory Extract
每个 Chat Agent 实例，均有自己专属的 [Memory Extract Agent](/docs/impl-spec/memory-extract-agent-spec.md) 实例。

**Memory Extract 不再无条件每轮触发**，改为由 Chat Agent 通过 `request_memory_extraction` 工具**显式触发**。

- Chat Agent 的 LLM 在本轮回复调用此工具 → `MainAgent` 在 `invoke()` 末尾构造 `ExtractInput`（含 Chat Agent 传入的 `reason` / `note`）并提交。
- 不调用工具 → 本轮不触发抽取，游标正常推进，内容自然成为后续轮次的 context_messages。
- 工具执行体仅设置 pending 标记（`self._pending_extract`），不直接 submit —— 确保 LLM 多步工具循环中切片正确的唯一时机是 `invoke()` 末尾。

见 [chat-agent-tools-spec.md](/docs/impl-spec/chat-agent-tools-spec.md) 的 `request_memory_extraction` 工具定义。

### 用户要求记住某知识点时的行为契约

当用户表达"记住 / 记下 / 帮我记"某 `target_lang` 知识点（单词/短语/语法点/语用）时，Chat Agent **必须先在本轮回复中产出该知识点的实际内容**（释义/解释/用法/举例，按上文「查单词」「翻译」要求用 `dest_lang` 给出），**然后**再调用 `request_memory_extraction(reason="user_explicit_request")` 并附"已提交笔记请求"提示。

**为什么不能只回"已提交笔记请求"**：

Memory Extract Agent 的 `mean_summary` 真实性约束要求事实必须来自 `new_messages` 里的 `ToolMessage` 或 `AIMessage.content`（见 [memory-extract-agent-spec.md「mean_summary 真实性约束」](/docs/impl-spec/memory-extract-agent-spec.md#mean_summary-真实性约束)）。当前实现没有查词工具，释义完全由 LLM 在 `AIMessage.content` 中产出。如果 Chat Agent 只回"已提交笔记请求"而不产出释义，`new_messages` 中关于该知识点没有任何事实内容，下游要么抽不到，要么被迫自造（违反真实性约束）。两类失败都是同一根因的两种表现。

纠正事项（用户写错被纠正）的场景天然满足事实来源（用户原句 + Agent 纠正都在本轮对话里），无需额外动作。


## 笔记删除与编辑

Chat Agent 可按用户口头请求删除或编辑已有的笔记条目（知识点文件）。**无 slash 命令**，由 LLM 识别意图 #9（笔记删除）/ #10（笔记编辑）后驱动。system prompt 中 `### 笔记删除` 与 `### 笔记编辑` 节给出完整流程约束（见 `agent.py` `_build_system_prompt()` 中 vault_available 分支）。

### 主流程（删除 / 编辑共四步）

1. **定位文件**
   - 优先从对话历史中推断 `file_path`：如 Memory Writer 通知的 `updated_files`（见下文「系统事件处理」节），或之前已定位过的文件
   - 推断失败时，用 `vault_mcp_search` 搜索 top 4，逐一 `vault_mcp_read` 确认最匹配的文件
   - 定位到文件后，`vault_mcp_read` 读取其 frontmatter 获取 `title` 和 `item_type`

2. **必须确认**
   - 执行前**必须**向用户确认目标笔记的 `title` 和 `item_type`
   - 确认格式示例：「请确认：目标笔记 title=「曖昧」, item_type=vocab（词汇），对吗？」
   - 用户确认后才可调用 `memory_writer_action` 工具
   - 用户否认并提供新提示 → 重新定位（回到步骤 1）
   - 用户取消 → 不执行

3. **执行**
   - **删除**：`memory_writer_action(operation="delete", file_path="...")`
   - **编辑**：
     1. 必须先 `vault_mcp_read(path=file_path)` 加载最新原文件
     2. 在内存中按用户要求编辑：
        - **正文**：去除 markdown frontmatter 部分后编辑
        - **Frontmatter**：保护字段（ulid / slug / type / created_at / timestamp / schema_version / first_seen / last_seen / seen_count）**必须原样保留**，可编辑字段（title / description / description_in_target_lang / tags 等）按用户要求修改
     3. 调用 `memory_writer_action(operation="edit", file_path="...", body="<新正文>")`，可选传入 `frontmatter="<完整 YAML 文本>"` 以同步编辑 frontmatter；保护字段值会被 Writer 端强制保留原值

4. **转告结果**
   - 工具返回 JSON 后，如实告知用户操作结果

### 同步语义

`memory_writer_action` 是**同步**调用：工具内部 `await memory_writer.execute_action_async(entry)` 等待 Memory Writer Agent daemon thread 完成（30s 超时保护），结果作为 `ToolMessage` 回到 LLM。

- **不经过** Memory Extract Agent（跳过结构化抽取，因为没有新知识点要抽取）
- **不发** `SystemNotice`（与创建流程不同；结果通过 future 同步回传，不经过事件队列）

工具定义见 [chat-agent-tools-spec.md — 笔记删除与编辑](/docs/impl-spec/chat-agent-tools-spec.md)。
Memory Writer 端的实现见 [memory-writer-agent-spec.md — 笔记删除与编辑](/docs/impl-spec/memory-writer-agent-spec.md#笔记删除与编辑同步-action-流程)。

### 约束

- **禁止**在未确认的情况下调用 `memory_writer_action`
- **禁止**凭空编造 `file_path`；必须来自定位步骤或对话历史
- 调用 `memory_writer_action` 时 `body` 参数必须是**完整正文**，不能是片段
- 删除/编辑时定位文件用到的就是「Memory Vault 只读访问」一节的 5 个只读 vault 工具

### 手工测试用例

Case1：新增笔记，然后编辑

1. 记住 ambiguous 这个词
2. 在笔记中增加: gcc 时常有出现这个单词

Case2：编辑不在 session context 的笔记

1. 在 ambiguous 这个词的笔记中增加: gcc 时常有出现这个单词
2. 再增加一个例句: the election result was ambiguous


## Agent tools

参考： [chat-agent-tools-spec.md](/docs/impl-spec/chat-agent-tools-spec.md)

### memory_writer_action（笔记删除/编辑）

同步工具，删除或编辑已有笔记条目。`_refresh_agent_if_needed()` 重建 agent 时通过工厂 `make_memory_writer_action_tool(...)` 注入，闭包绑定 `target_lang` / `interface_lang` / `chat_session_id` / `channel_name`。详见上文「笔记删除与编辑」节与 [chat-agent-tools-spec.md](/docs/impl-spec/chat-agent-tools-spec.md)。

### vault 工具（只读）

见 [chat-agent-tools-spec.md](/docs/impl-spec/chat-agent-tools-spec.md) 中 [vault 工具集](#vault-记忆库只读) 节。
通过 Vault MCP Server 提供（[vault-mcp-spec.md](/docs/impl-spec/vault-mcp/vault-mcp-spec.md)），复用 `mem_writer_mcp_client.mcp_vault_connection`，过滤为只读子集。

## 系统事件处理

`MainAgent.ahandle_system_notice(notice: SystemNotice)` 处理后台系统通知。

通知以 `[系统通知]` 前缀的 HumanMessage 注入 `_messages`，走 LLM 决定是否告知用户。
与用户消息处理分开，不触发 typing hint，跳过 Memory Extract（知识已被 Writer 写入）。

System prompt 中有一节 `## 系统事件通知`，告知 LLM 收到通知后的决策规则。

详见：
- [session.md — 事件队列与通知处理](/docs/impl-spec/session.md)
- `src/everlingo/gateway/session_events.py` — 事件类型定义

## Observability
所有发给 LLM 的请求都写入日志文件。见 [observability.md](/docs/impl-spec/observability.md) 。 日志 level 是 debug 。


## Agents 数据流水线

```
Chat Agent  →  [显式触发]  →  Memory Extract Agent  →  Memory Writer Agent
(对话回复)     (request_memory_extraction 工具)     (筛选 + 结构化抽取)       (异步写 vault)
```

- Chat Agent 的 LLM 通过 `request_memory_extraction` 工具决定是否驱动记忆抽取。
- 工具调用设置 pending 标记，`MainAgent.invoke()` 末尾统一提交 `ExtractInput`。
- [Memory Extract Agent](/docs/impl-spec/memory-extract-agent-spec.md) 信任上游的触发意图，跳过"是否值得记"的语义筛选，专职结构化抽取。
- [Memory Writer Agent](docs/impl-spec/memory-writer-agent-spec.md) 异步写入 memory vault。

