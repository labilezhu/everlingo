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
- 提供 `voice_speak` 工具（见 [tools.md](/docs/impl-spec/tools.md)）

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

## Agent tools

参考： [tools](/docs/impl-spec/tools.md)

## 同步对话到 memory writer agent
在每轮用户对话结束后， Chat Agent 应该把新的对话 memory entry 同步给 [Memory Writer Agent](/docs/impl-spec/memory-writer-agent-spec.md).

### memory writer agent 同步筛选

哪些 memory entry 应该同步给 Memory Writer Agent，哪些该跳过：

应跳过的内容：
- 与学习 `目标学习语言` 无关的信息。
- 琐碎/显而易见的信息
- 原始数据转储：大段内容，数据量过大(超过1000字)，不适合存入记忆
- 会话特有的临时信息：如用户要求你当一个图书管理员角色，类似这样只影响当前会话的信息。
- 在当前会话中，之前已经有同步过的内容，不要重复同步
- 用户偏好，因为用户偏好应该保存在 USER.md

应主动保存的内容:
- 用户明确要求：“记住 somebody used to do something 这个短语” 
- 纠正事项：发现信息生产源头是用户自己 且 用户未预期到的 且 `目标学习语言`方面的任何错误。

应主动询问是否记住的内容：
- 同一个对话会话中，多次出现的与`目标学习语言`相关的知识
- 明显难记忆或生僻小众的`目标学习语言`相关的知识
- 通过用户偏好或个性设置，发现很容易出错的知识。如，中国程序员很容易回答 Aren't you a programmer? 为 No


## Observability
所有发给 LLM 的请求都写入日志文件。见 [observability.md](/docs/impl-spec/observability.md) 。 日志 level 是 debug 。


