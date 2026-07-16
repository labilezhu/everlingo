# Memory Extract Agent

负责从由 Chat Agent 通过 `request_memory_extraction` 工具显式触发的一轮对话中，提取结构化知识点 entries，转交给 [Memory Writer Agent](/docs/impl-spec/memory-writer-agent-spec.md) 异步写入。

**不再自主判断"本轮是否值得抽取"**——该决策已由上游 Chat Agent 完成。


## 筛选规则

**上游 Chat Agent 已通过 tool 调用决定"值得抽取"。** Extract Agent 不再自主判断"应保存"语义规则（用户明确要求记住 / 纠正事项），而是信任上游的 `reason` 字段映射为 `why_want_to_save_memory`。

### 仅保留结构性跳过规则

应跳过的内容：
- 与学习 `目标学习语言` 无关的信息。
- 琐碎/显而易见的信息
- 原始数据转储：大段内容，数据量过大(超过1000字)，不适合存入记忆
- 会话特有的临时信息：如用户要求你当一个图书管理员角色，类似这样只影响当前会话的信息。
- 从背景上下文中抽取：`context_messages` 段仅供生成 `conversation_context`，禁止从中抽取知识点。抽取来源仅限 `new_messages` 段。
- 用户偏好，因为用户偏好应该保存在 USER.md

## 职责边界

**做**：
- 根据 Chat Agent 传递的 `reason` / `note`，提取结构化 entries。
- 保留结构性筛选（字数上限、来源边界、与 target_lang 无关的兜底跳过）。

**不做**：
- 不读写文件（Writer 的事）
- 不读 vault（本阶段记忆只写不读）
- 不与用户交互、不产生用户可见输出
- 不做跨会话 dedup（本阶段只写不读，无法跨会话）
- 不做工具调用（无 tools，纯结构化输出的 LLM call）
- **不做"是否值得记"的语义判断**——该决策由 Chat Agent 的 `request_memory_extraction` 工具调用完成

## 异步执行

Memory Extract Agent **异步**执行，不阻塞用户回复。由 Chat Agent 显式触发：

```
Chat Agent LLM 调用 request_memory_extraction(reason, note)
  → MainAgent._pending_extract = (reason, note)          # 工具内仅设标记
  → MainAgent.invoke() 末尾：
       if _pending_extract:
         submit(ExtractInput)                             # 统一提交
         _pending_extract = None
       _extract_cursor = len(_messages)                   # 游标始终推进
  → replies (立即返回给用户，零延迟)
  → self._extract_agent.submit(ExtractInput)              # 入队即返回
        ↓ [extract daemon thread, per-instance]
  MemoryExtractAgent._run_loop()
        ↓ consume ExtractInput
  extract(input)  →  entries
        ↓ 成功且非空
  gateway.memory_writer.enqueue(entries)                  # 转交 Memory Writer Agent 队列
```

- 每个 MainAgent 实例拥有自己的 Memory Extract Agent 实例与 daemon thread（见"生命周期"）。
- `submit()` 仅入队，不阻塞。
- Extract 完成后把 entries 转给全局单例 Memory Writer 的队列。
- daemon thread (`daemon=True`)，进程结束直接丢弃未处理项，可接受丢失（与 Memory Writer Agent 一致）。

## 生命周期与状态

### 实例归属

**不放 gateway.py 模块级**。每个 `MainAgent` 实例在 `__init__` 中创建并持有自己的 `MemoryExtractAgent` 实例，因为两者会话级状态相关。

```python
class MainAgent:
    def __init__(self, ...):
        ...
        self._extract_agent = MemoryExtractAgent(
            memory_writer=gateway_memory_writer,   # 全局单例引用
            chat_session_id=self._session_id,
            channel_name=...,
            target_lang=...,
            interface_lang=...,
        )
        self._extract_agent.start()
```

### 会话级状态

Memory Extract Agent **无状态**。所有会话级 dedup 由 `MainAgent` 通过 **extract 游标** 完成：

- `MainAgent._extract_cursor: int` —— 已遍历过的 `_messages` 长度。每次 `invoke()` 末尾：
  - 若 `_pending_extract` 已设置：构造 `ExtractInput` 并 submit。
    - `new_messages = self._messages[self._extract_cursor:]`（本轮往返，唯一抽取来源）
    - `context_messages = _tail_recent_turns(self._messages[:self._extract_cursor], limit=19)`（背景上下文，仅供生成 `conversation_context`）
  - **无论是否触发抽取**，游标均推进 `self._extract_cursor = len(self._messages)`。未触发轮自然成为后续触发的背景上下文。
  - 即使后续 extract LLM call 失败也推进（与 daemon thread "可接受丢失"语义一致，避免失败轮次在下次 invoke 被重抽）。

游标放在 MainAgent 而非 Extract Agent：Extract Agent 消费 `ExtractInput` 即完成全部判断，无状态、可序列化、可测试。Extract Agent 自身不再持有任何会话级状态。

下阶段加"主动询问是否记住"逻辑时，再扩 `session_asked_headwords: set` 与 `session_ask_count: int`（届时再决定归属），本阶段不实现。

### 生命周期

- `MainAgent.__init__` 创建并 `start()` Extract Agent。
- 进程退出靠 daemon thread 自动结束，不显式 shutdown。
- Extract Agent 持有全局 `memory_writer` 引用，用于转交 entries。

## 输入规范

Extract Agent 的输入是**结构化对象**而非自由文本，由 `MainAgent.invoke()` 在返回 replies 后构造：

```python
@dataclass
class ExtractInput:
    # —— 本轮 MainAgent._intent_mode 快照 ——
    intent_mode: str | None      # None=自动, "dict"=查词, "translate"=翻译

    # —— 本轮新增 messages（自上次 extract 游标以来）——
    # 唯一允许的抽取来源。通常含本轮 HumanMessage + 其后的 AIMessage / ToolMessage。
    # 必须保留 ToolMessage —— 查词/翻译工具返回是 mean_summary 的事实来源。
    new_messages: list[Message]

    # —— 背景上下文（不含本轮）——
    # 最近最多 19 轮，仅供 LLM 生成 conversation_context 字段。
    # 禁止从中抽取知识点。
    context_messages: list[Message]

    # —— Chat Agent 触发原因 ——
    # "user_explicit_request" / "correction" / "other"
    # 由 request_memory_extraction 工具传入，_post_process 映射为 why_want_to_save_memory
    reason: str | None = None

    # —— Chat Agent 可选语义提示 ——
    note: str = ""
```

### 设计说明

- `chat_session_id / channel_name / target_lang / interface_lang` 这些会话元数据在 Extract Agent 创建时由 MainAgent 传入，作为实例属性持有，每轮 extract 复用，不放入 `ExtractInput`。避免每轮重复传递，也让 ExtractInput 更纯粹。
- Extract Agent 自身无会话级状态（dedup 由 MainAgent 游标解决），`ExtractInput` 自包含、可序列化、可测试。
- `new_messages / context_messages` 均来自 `MainAgent._messages`（已排除注入的 SystemMessage，可直接切片）。`new_messages = _messages[cursor:]`，`context_messages = _tail_recent_turns(_messages[:cursor], limit=19)`。

### "轮"的定义

1 轮 = 1 个 `HumanMessage` + 其后到下一个 `HumanMessage` 之前的所有 `AIMessage` / `ToolMessage`。即一个 user turn 的完整往返。

`context_messages` 取最近最多 19 轮（不含本轮）。`new_messages` 通常为 1 轮（本轮往返），但若 MainAgent 在一次 invoke 内向 `_messages` 追加了多段 AI/Tool 片段（如多步工具调用），`new_messages` 会含整段——这是符合预期的，整段都属于"本轮"。

### 为什么分离 new / context

旧设计每轮都把最近 20 轮（含本轮）整体交给 LLM，LLM 视角里旧轮次与当前轮平等，没有任何信号告诉它"这段已抽过"。会话内 dedup 靠 `session_seen_headwords` 字符串匹配，而 headword 由 LLM 生成、即使 `temperature=0` 也无法稳定到逐字一致（同一历史片段两次抽取得到不同 headword），导致：

- 同一段历史被反复抽取；
- 两次 headword 不一致，事后 dedup 失效。

新设计把"本轮新增"与"背景上下文"在输入侧硬隔离：抽取来源仅限 `new_messages`，`context_messages` 仅用于生成 `conversation_context`。从而在 LLM 层面就避免重复抽取，无需依赖 headword 字符串匹配。

## 输出规范

见： [Memory Extract Agent 输出规范](/src/everlingo/mem/vault/templates/default/spec/memory_extract_output_spec.md)

### 日志要求
输出的所有 entries ，都需要有 info 级别的日志输出所有字段的内容。

### 字段来源约定

便于实现与测试，明确每个字段的来源：

- `chat_session_id / channel_name / user_intent / lang / interface_language`：从 Extract Agent 实例属性与 `ExtractInput.intent_mode` 透传，LLM 不应修改。实现时拿到 LLM 输出后**用实例属性值覆盖**，保证一致性。
  - `user_intent` 映射：`intent_mode="dict"` → `"dict"`；`"translate"` → `"translate"`；`None` → `"None"`。
  - `lang` = 实例属性 `target_lang`。
  - `interface_language` = 实例属性 `interface_lang`（界面语言，Memory Writer 用作 markdown 正文的主要书写语言，见 `src/everlingo/mem/vault/vault_spec.md`「Markdown 文件使用什么语言编写」）。
- `entry_id / timestamp`：**代码生成**，不让 LLM 生成。
  - `entry_id`：uuid4。
  - `timestamp`：Extract 执行时刻，格式 `yyyy-mm-dd HH:MM:SS`，GMT+8。
- `item_type / why_want_to_save_memory / title`：LLM 生成。
- `new_messages / context_messages`：从 `ExtractInput` 透传（渲染后的字符串列表，用于填入 `MemoryEntry`）。
- 注意：`conversation_context` 不再由 Extract Agent 生成，改由 Memory Writer Agent 在写入时根据 `new_messages` / `context_messages` 生成。

### why_want_to_save_memory 枚举

`why_want_to_save_memory` 不再由 LLM 判断，而是在 `_post_process` 阶段根据 `reason` 参数映射：

| `reason` 值 | 映射后的 `why_want_to_save_memory` |
|---|---|
| `user_explicit_request` | `用户明确要求记住知识点` |
| `correction` | `纠正事项` |
| `other` | `Chat Agent 判定` |

`reason` 为 None 时（测试兼容）保留 LLM 生成值。`Chat Agent 判定` 为新枚举值，反射上游 Chat Agent 的判断。


## conversation_context 生成

`conversation_context` 不再由 Extract Agent 生成，改为从 `ExtractInput` 的 `new_messages` / `context_messages` 透传给 Memory Entry，由 Memory Writer Agent 在写入时生成。Extract Agent 需确保这两个字段填充为渲染后的消息文本列表（字符串），供 Writer Agent 的 LLM 参考。

## 失败处理

Extract LLM call 异常或结构化输出解析失败时：

- `logger.exception(...)` 记 error 日志，含 `chat_session_id` 与本轮可辨识信息。
- 丢弃本轮 entries，**不调用** `memory_writer.enqueue`。
- 不影响用户（用户早已收到 replies）。
- 不影响后续轮次（daemon thread 继续消费队列）。

## 实现

应实现于：`/src/everlingo/mem/agents/mem_extract_agent.py`。

- 用 langchain 的 LLM 调用 + **structured output**（`with_structured_output`），不是 `create_agent`（无工具）。
- 有自己的 system prompt。**不需要注入 vault_spec**（不碰文件），但需要注入筛选规则与输出 schema。
- daemon thread + `queue.Queue`。
- 每次执行 extract 时，调用 `load_user_doc()` 读取最新 USER.md 内容注入 system prompt。无需 mtime 刷新机制——extract 时读最新即可，文件 IO 相对 LLM call 可忽略。USER.md 为空时跳过该节。USER.md 有 500 字上限（由 `user_doc_set` 工具约束），全文注入可接受，不需要截断。

### System prompt 要点

- 角色：知识点抽取器，不与用户对话。
- 输入字段含义说明（`intent_mode` / `reason` / `note` / `new_messages` / `context_messages`，以及实例属性中的会话元数据）。
- **不再自主判断"是否值得抽取"**：上游 Chat Agent 已通过 `request_memory_extraction` 工具触发，`reason` 字段即为触发原因。LLM 应按 `reason` 映射输出 `why_want_to_save_memory`（`user_explicit_request` → `用户明确要求记住知识点`，`correction` → `纠正事项`，`other` → `Chat Agent 判定`）。
- **抽取边界硬约束**：只允许从 `new_messages` 中抽取知识点；`context_messages` 仅用于生成 `conversation_context`，其中出现过的事实不得作为 entry 输出。
- 筛选规则（本轮仅保留结构性跳过规则：字数上限、来源边界、与 target_lang 无关跳过等）。
- 输出 schema、字段说明（由运行期通过 MCP `compile_prompt` 工具加载并展开 include：`memory_extract_spec.md` → `memory_extract_output_spec.md` → `mem_entry_spec.md`；不再本地兜底）。
- `conversation_context` 不在此生成；`new_messages` / `context_messages` 均透传给 Memory Entry 供 Writer Agent 使用。
- 注入 USER.md 内容（标题降级，防止与 prompt 外层结构冲突），用于筛选判断。参考 `agent.py` 的 `_demote_headings()` 实现标题降级。
- 只输出 JSON，不输出解释性文字。

### Prompt 文件加载

`memory_extract_spec.md` 通过 `{{ include }}` 引用了 `memory_extract_output_spec.md`（后者又引用了 `mem_entry_spec.md`）。System prompt 在 `_build_system_prompt()` 中通过 MCP `compile_prompt` 工具动态编译 `spec/memory_extract_spec.md`，一步得到完整展开后的 spec 文本。MCP server 不可用（`IndexerOfflineError`）或 spec 文件缺失时，本轮 extract 失败丢弃（与 LLM call 失败一致），不再回退至 `PackageSource`。

## 已知简化 / 待评估

- **模型**：使用独立工厂 `create_extract_llm()`（见 `src/everlingo/llm.py`），与主对话同 model / callbacks / tracing，唯一差异是 `temperature=0`。抽取任务要求结构化、确定性输出，0.7 会带来字段漂移；已实施独立配置，不再复用 `create_llm()`。
- **失败轮次丢失**：extract LLM call 失败时本轮 `new_messages` 不再重抽（游标已在 submit 前推进），与 daemon thread "可接受丢失"语义一致。
- **跨会话 dedup**：本阶段 Extract Agent 不读 vault，无法跨会话 dedup，推迟到下阶段读取能力上线。
- **语义筛选职责迁移**：Extract Agent 不再自主判断"是否值得抽取"，该决策由 Chat Agent 的 `request_memory_extraction` 工具调用完成。Extract Agent 保留结构性跳过规则（字数上限、来源边界、target_lang 无关）。这样避免了两个 LLM 对同一轮进行重复的"是否值得记"判断。
- **context 上限 19 轮**：经验值，若发现不足或过多再调整。`context_messages` 取 `MainAgent._messages[:cursor]` 的尾部 turn 截断，不单独持久化。


## 人工手工测试用例
可用对话样例观察：
- 「记住 ambiguous 这个词」→ 触发"用户明确要求记住知识点"
- 「I goes to school」被纠正 → 触发"纠正事项"
- 我是个 Software engineer. 有人问我： aren't you a software engineer? 我回答了： No, I'm not
- 查询 god。你记住 god 这个单词，写入记忆知识库
- If I will see him, I'll tell him.
- 正常查词/翻译 → 应被跳过（无 entries 日志）
- 同一段纠正历史在后续闲聊轮中不再被抽取（因后续轮 `new_messages` 不含该历史，仅作 `context_messages` 背景）
- 解释一下 The best is yet to come 这句话，帮我记下