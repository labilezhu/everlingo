# Memory Extract Agent

负责从刚刚结束的一轮对话中，筛选出值得记入 [memory vault](/docs/impl-spec/worksplace/memory-vault-spec.md) 的知识点，并输出结构化 entries，转交给 [Memory Writer Agent](/docs/impl-spec/memory-writer-agent-spec.md) 异步写入。


## 筛选规则

### 最终产品规则
哪些 memory entry 应该同步给 Memory Writer Agent，哪些该跳过：

应跳过的内容：
- 与学习 `目标学习语言` 无关的信息。
- 琐碎/显而易见的信息
- 原始数据转储：大段内容，数据量过大(超过1000字)，不适合存入记忆
- 会话特有的临时信息：如用户要求你当一个图书管理员角色，类似这样只影响当前会话的信息。
- 在当前会话中，之前已经有同步过的内容，不要重复同步
- 用户偏好，因为用户偏好应该保存在 USER.md

应主动保存的内容:
- 用户明确要求记住知识点 ：“记住 somebody used to do something 这个短语” 
- 纠正事项 ：发现信息生产源头是用户自己 且 用户未预期到的 且 `目标学习语言`方面的任何错误。
- 推断用户需要记住

应主动询问是否需要记住知识点：
- 同一个对话会话中，同一个知识点出现到达2次的。而且相同知识点之前没有询问过是否需要记住。
- 明显难记忆或生僻小众的`目标学习语言`相关的知识
- 通过用户偏好或个性设置，发现很容易出错的知识。如，中国程序员很容易回答 Aren't you a programmer? 为 No

不应主动询问是否记住知识点的场景：
- 同一会话中，主动询问是否记住已经超过 3 次。影响应用体验

### 当前阶段产品规则

#### 规则优先级

当规则间冲突时，按以下优先级判断（高优先级先于低优先级）：

1. **用户明确要求记住** —— 最高，即使知识点对用户"显而易见"也应保存。
2. **纠正事项** —— 用户自己产出的 target_lang 错误被纠正。
3. **跳过规则**（与 target_lang 无关 / 用户偏好类 / 会话内已抽取 / 琐碎显而易见）。

#### 应保存

1. **用户明确要求记住**：如「记住 X 这个短语」「帮我记下 X」。
2. **纠正事项**：信息生产源头是用户自己，且用户未预期到的，且 `target_lang` 方面的错误。如用户写 "I goes to school"，Agent 纠正为 "I go to school"。

#### 应跳过

1. 与 `target_lang` 无关。
2. 用户偏好类（应入 USER.md，由 Chat Agent 处理）。
3. 原始数据转储：单条 Message 文本超 1000 字时，该 Message 不作为 `mean_summary` 的事实来源，但轮内其它知识点仍可抽取。
4. 会话内已抽取：`headword` 已在 `session_seen_headwords` 中。
5. 琕碎/显而易见。

#### 本阶段不做（推迟到下一阶段）

- 推断用户需要记住
- 主动询问是否记住

## 职责边界

**做**：分析本轮对话，判断该不该记、记什么，输出结构化 entries。

**不做**：
- 不读写文件（Writer 的事）
- 不读 vault（本阶段记忆只写不读）
- 不与用户交互、不产生用户可见输出
- 不做跨会话 dedup（本阶段只写不读，无法跨会话）
- 不做工具调用（无 tools，纯结构化输出的 LLM call）

## 异步执行

Memory Extract Agent **异步**执行，不阻塞用户回复：

```
MainAgent.invoke()
  → replies (立即返回给用户，零延迟)
  → self._extract_agent.submit(ExtractInput)        # 入队即返回
        ↓ [extract daemon thread, per-instance]
  MemoryExtractAgent._run_loop()
        ↓ consume ExtractInput
  extract(input)  →  entries
        ↓ 成功且非空
  gateway.memory_writer.enqueue(entries)             # 转交 Memory Writer Agent 队列
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

Memory Extract Agent 是有状态的。本阶段会话级状态只有一个：

- `session_seen_headwords: list[str]` —— 本会话内已抽取过的 headword，用于会话内 dedup。每次 extract 产出 entries 后，把新增 headword 追加进列表。

下阶段加"主动询问是否记住"逻辑时，再扩 `session_asked_headwords: set` 与 `session_ask_count: int`，本阶段不实现。

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

    # —— 最近最多 20 轮对话（含本轮）——
    # 顺序与 LLM 实际收到/产出一致
    # 必须排除注入的 SystemMessage（模式提示）
    # 必须保留 ToolMessage —— 查词/翻译工具返回是 mean_summary 的事实来源
    context_messages: list[Message]
```

### 设计说明

- `chat_session_id / channel_name / target_lang / interface_lang` 这些会话元数据在 Extract Agent 创建时由 MainAgent 传入，作为实例属性持有，每轮 extract 复用，不放入 `ExtractInput`。避免每轮重复传递，也让 ExtractInput 更纯粹。
- `session_seen_headwords` 是 Extract Agent 内部状态，不放入 `ExtractInput`。这样 ExtractInput 可序列化、可测试，不耦合状态。
- `context_messages` 取最近最多 20 轮（含本轮），来源为 `MainAgent._messages` 尾部截取（`_messages` 已排除注入的 SystemMessage，可直接用）。

### "轮"的定义

1 轮 = 1 个 `HumanMessage` + 其后到下一个 `HumanMessage` 之前的所有 `AIMessage` / `ToolMessage`。即一个 user turn 的完整往返。

20 轮 ≈ 20 个 `HumanMessage` 触发的完整对话片段。若历史不足 20 轮则全部传入。

### 为什么用 20 轮而非本轮 delta

- `conversation_context` 字段需要跨轮上下文才能生成有意义的内容（如"用户在学习日语小说《罗生门》时查词"可能需要前几轮的背景）。
- 为下阶段"同一知识点出现 2 次"的询问规则打基础（虽然本阶段不做，但上下文已就位）。
- "用户明确要求记住"与"纠正事项"在最新轮即可判断，20 轮 context 不影响这两条规则的触发，只是提供更充分的判断背景。

## 输出规范

schema 与 [memory-writer-agent-spec.md](/docs/impl-spec/memory-writer-agent-spec.md) 的 conversation memory entries 一致

### 日志要求
输出的所有 entries ，都需要有 info 级别的日志输出所有字段的内容。

### 字段来源约定

便于实现与测试，明确每个字段的来源：

- `chat_session_id / channel_name / user_intent / lang`：从 Extract Agent 实例属性与 `ExtractInput.intent_mode` 透传，LLM 不应修改。实现时拿到 LLM 输出后**用实例属性值覆盖**，保证一致性。
  - `user_intent` 映射：`intent_mode="dict"` → `"dict"`；`"translate"` → `"translate"`；`None` → `"None"`。
  - `lang` = 实例属性 `target_lang`。
- `entry_id / timestamp`：**代码生成**，不让 LLM 生成。
  - `entry_id`：uuid4。
  - `timestamp`：Extract 执行时刻，格式 `yyyy-mm-dd HH:MM:SS`，GMT+8。
- `item_type / why_want_to_save_memory / headword / mean_summary / conversation_context`：LLM 生成。

### why_want_to_save_memory 枚举

本阶段只允许两个值：
- `用户明确要求记住知识点`
- `纠正事项`

其余（推断用户需要记住 / 主动询问相关）推迟到下一阶段。


## mean_summary 真实性约束

`mean_summary` **必须基于 `context_messages` 中 `ToolMessage` 的事实内容**（查词/翻译工具的返回），不允许 LLM 自由发挥或引入外部知识。本轮无工具返回（纯问答）时，基于 Agent 回复中给出的解释。此约束写进 system prompt，并在测试用例中验证。

USER.md 仅用于**筛选判断**（判断"琐碎/显而易见""与 target_lang 相关性""用户偏好类应跳过"等），`mean_summary` 保持事实性、不个性化。否则 mean_summary 会偏离工具返回的真实释义，违反真实性约束。

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
- 输入字段含义说明（`intent_mode` / `context_messages`，以及实例属性中的会话元数据）。
- 筛选规则（本阶段精简版）与规则优先级。
- 输出 schema 与字段来源约定。
- mean_summary 真实性约束（基于 ToolMessage 事实，不个性化）。
- 注入 `session_seen_headwords` 列表，告诉 LLM 这些 headword 已记过，跳过不再输出。
- 注入 USER.md 内容（标题降级，防止与 prompt 外层结构冲突），用于筛选判断。参考 `agent.py` 的 `_demote_headings()` 实现标题降级。
- 只输出 JSON，不输出解释性文字。

## 已知简化 / 待评估

- **模型**：本阶段复用 `create_llm()`（与主对话同配置、同 temperature=0.7），简化设计。若后续发现 temperature=0.7 影响抽取稳定性，再考虑在 `llm.py` 增加 `create_extract_llm()` 独立配置（更低 temperature）。
- **会话内 dedup 基于 headword 字符串匹配**：粗糙，"曖昧" 与 "暧昧" 不会判重。本阶段可接受，下阶段读取能力上线后可改进。
- **context 上限 20 轮**：经验值，若发现不足或过多再调整。context_messages 取 `MainAgent._messages` 尾部截取，不单独持久化。


## 人工手工测试用例
可用对话样例观察：
- 「记住 ambiguous 这个词」→ 触发"用户明确要求记住知识点"
- 「I goes to school」被纠正 → 触发"纠正事项"
- 正常查词/翻译 → 应被跳过（无 entries 日志）
- cat 查词两次 → 第二次应被 session_seen_headwords dedup