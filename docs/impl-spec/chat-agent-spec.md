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


## 用户显式模式指定

用户可通过 `/dict`、`/translate`、`/`、`/help` 命令显式指定当前会话模式，由代码（而非 LLM）处理：

| 命令 | 行为 |
|---|---|
| `/dict` | 设置 `_intent_mode = "dict"`，后续消息发给 LLM 前注入 `SystemMessage("当前模式为「查词」...")` |
| `/translate` | 设置 `_intent_mode = "translate"`，后续消息注入 `SystemMessage("当前模式为「翻译」...")` |
| `/` | 重置 `_intent_mode = None`，回到自动意图识别 |
| `/help` | 显示可用命令及当前模式 |
| 其他 `/` 开头 | 提示未知命令 |

实现位置：`MainAgent._handle_command()` + `MainAgent.invoke()`。

关键设计：
- 模式切换命令**不经过 LLM**，直接返回，不写入 `self._messages` 历史
- 模式提示以 **`SystemMessage`** 形式注入 `messages_for_llm` 列表，不污染用户的原文 `HumanMessage`
- `self._messages` 持久化历史中排除注入的 `SystemMessage`，保留 `HumanMessage` + `AIMessage` + `ToolMessage`
  - `ToolMessage` 必须保留：多轮对话中 LLM 需要工具结果上下文（例如追问"刚才查的那个词的近义词"时需要看 voice_speak 的 ToolMessage）
- System prompt 中的 `## 用户显式模式指定` 节告知 LLM 此机制，明确优先级高于自动意图识别
- 模式在 agent 重建（配置变更）后依然保持（`_intent_mode` 是实例变量）

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
- 命令路径（`/dict` 等）和异常路径 → 返回单元素列表 `[MessageEvent(...)]`

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
你只读不写；写入由 Memory Extract Agent 异步完成。
```

vault 离线时改为：
```
## 记忆库访问
记忆库暂不可用，请告知用户稍后再试。
```

## Memory Extract
每个 Chat Agent 实例，均有自己专属的 [Memory Extract Agent](/docs/impl-spec/memory-extract-agent-spec.md) 实例。用户从对话中提炼要记忆的对象。见 [Memory Extract Agent](/docs/impl-spec/memory-extract-agent-spec.md) 中的 “## 输入规范” 。

### 用户要求记住某知识点时的行为契约

当用户表达"记住 / 记下 / 帮我记"某 `target_lang` 知识点（单词/短语/语法点/语用）时，Chat Agent **必须先在本轮回复中产出该知识点的实际内容**（释义/解释/用法/举例，按上文「查单词」「翻译」要求用 `dest_lang` 给出），**然后**再附"已提交笔记请求"提示。

**为什么不能只回"已提交笔记请求"**：

Memory Extract Agent 的 `mean_summary` 真实性约束要求事实必须来自 `new_messages` 里的 `ToolMessage` 或 `AIMessage.content`（见 [memory-extract-agent-spec.md「mean_summary 真实性约束」](/docs/impl-spec/memory-extract-agent-spec.md#mean_summary-真实性约束)）。当前实现没有查词工具，释义完全由 LLM 在 `AIMessage.content` 中产出。如果 Chat Agent 只回"已提交笔记请求"而不产出释义，`new_messages` 中关于该知识点没有任何事实内容，下游要么抽不到，要么被迫自造（违反真实性约束）。两类失败都是同一根因的两种表现。

纠正事项（用户写错被纠正）的场景天然满足事实来源（用户原句 + Agent 纠正都在本轮对话里），无需额外动作。

## Agent tools

参考： [chat-agent-tools-spec.md](/docs/impl-spec/chat-agent-tools-spec.md)

### vault 工具（只读）

见 [chat-agent-tools-spec.md](/docs/impl-spec/chat-agent-tools-spec.md) 中 [vault 工具集](#vault-记忆库只读) 节。
通过 Vault MCP Server 提供（[vault-mcp-spec.md](/docs/impl-spec/vault-mcp/vault-mcp-spec.md)），复用 `mem_writer_mcp_client.mcp_vault_connection`，过滤为只读子集。

## Observability
所有发给 LLM 的请求都写入日志文件。见 [observability.md](/docs/impl-spec/observability.md) 。 日志 level 是 debug 。


