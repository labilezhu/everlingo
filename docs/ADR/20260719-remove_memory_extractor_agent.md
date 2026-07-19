# ADR: 移除 Memory Extract Agent，Chat Agent 直接对接 Memory Writer Agent

- 状态：Accepted
- 日期：2026-07-19
- 决策参与方：用户、opencode
- 相关文档：
  - [Chat Agent](../impl-spec/chat-agent-spec.md)
  - [Memory Writer Agent](../impl-spec/memory-writer-agent-spec.md)
  - [Chat Agent Tools](../impl-spec/chat-agent-tools-spec.md)
  - [归档：Memory Extract Agent](../archived/memory-extract-agent-spec.md)
  - [归档：memory_extract_spec.md](../archived/memory_extract_spec.md)

---

## 1. 动机

当前从聊天中抽取记忆并写入笔记的流水线为三段：

```
Chat Agent → Memory Extract Agent → Memory Writer Agent
(对话回复)   (筛选 + 结构化抽取)    (异步写 vault)
```

Memory Extract Agent 在最近几次演进后职责已大幅萎缩：

1. **"是否值得抽取"判断迁移**：已由 Chat Agent 通过 `request_memory_extraction` 工具显式触发，Extract Agent 不再自主判断。
2. **抽取边界硬约束**：new/context 隔离靠 MainAgent 游标切片完成，Extract Agent 只消费已切好的 `ExtractInput`。
3. **结构化输出字段瘦身**：`ExtractLLMOutput` 仅剩 `item_type` / `title` / `why_want_to_save_memory` 三个字段；其余系统字段（`entry_id` / `timestamp` / 会话元数据 / `new_messages` / `context_messages`）均由 Extract Agent 的 `_post_process` 用代码补全。

剩余职责本质上是**对 Chat Agent 已产出的 `AIMessage.content` 做一次二次 LLM 结构化重组**——同源数据、类似语义判断、再调一次 LLM。这带来：

- 多一次 LLM 调用（成本、延迟、失败点）
- 多一个 daemon thread + queue（MainAgent 每实例一个 Extract Agent）
- 多一组数据结构（`ExtractInput` / `ExtractLLMOutput` / `LLMGeneratedEntry` / `EntryWriterProtocol`）与对应测试
- 两段 LLM 处理同一轮对话的语义判断职责重叠，长期维护负担增加

## 2. 合理性与可行性分析

### 2.1 合理性

**职责可上移**：Chat Agent 已经在 `AIMessage.content` 中产出释义/解释/用法/举例。让它顺带输出 `item_type` / `title` / `why_want_to_save_memory` 三个结构化字段，是已知上下文上的轻量增量，不会带来新的语义负担。

**状态面变薄**：删除 Extract Agent 后：
- 移除 per-instance daemon thread + queue
- 移除 `ExtractInput` dataclass 与游标配套的提交逻辑
- MainAgent 不再持有 `_extract_agent`
- 流水线从 3 段降为 2 段

**下游无需改动**：`MemoryWriterAgent.enqueue(list[MemoryEntry])` 接口与内部 `_process_batch` 流程保持不变。只换上游，不换下游。

**失败点减少**：少一次 LLM 调用、少一个 daemon thread、少一次 `IndexerOfflineError` 丢弃路径。

### 2.2 可行性

- **Tool args schema 强约束**：langchain tool 的 pydantic `args_schema` 可用 `Literal` 枚举锁定 `item_type` 与 `why_want_to_save_memory`，等价于原 `ExtractLLMOutput` 的 `with_structured_output` 约束。
- **系统字段代码补全**：`entry_id` / `timestamp` / 会话元数据 / `new_messages` / `context_messages` 由 `MainAgent.invoke()` 末尾从 `_messages` 切片 + 实例属性补全，逻辑与原 `_post_process` 等价，仅搬家到 MainAgent 侧。
- **Spec 动态加载**：`memory_extract_output_spec.md` 已由 MCP server 在 `create_vault` 时 `compile_prompt` 展开 `{{ include }}` 落盘到 vault。Chat Agent 通过 `vault_mcp_read(path="spec/memory_extract_output_spec.md")` 可直接拿到完整版本，无需在 system prompt 静态注入。

### 2.3 需要正视的风险

| 风险 | 缓解 |
|---|---|
| Chat Agent 过度抽取（丢掉 Extract 的结构性兜底） | 跳过规则迁移到 Chat Agent system prompt；`item_type` / `why` 用 Literal 枚举 |
| Chat Agent 未产出释义就调工具 | 保留「调用前必须已产出知识点实际内容」行为契约 |
| LLM 编造系统字段 | args_schema 不暴露系统字段，系统字段由代码补全 |
| 历史已记知识点被重复抽取 | system prompt 强调「只对当前轮新知识点调用」+ Writer 端按 title/slug 合并兜底 |
| LLM 跳过 `read spec` 直接调工具 | system prompt 强约束「必须先 read」+ 工具 args description 提示；测试观察 LLM 遵守度 |
| indexer 离线时 `read spec` 失败 | 与现有 vault 离线降级路径一致，LLM 反馈"加载规范失败，稍后再试" |

## 3. 架构变更内容

### 3.1 流水线变更

**变更前**（3 段）：

```
Chat Agent  →  [显式触发]  →  Memory Extract Agent  →  Memory Writer Agent
(对话回复)     (request_memory_extraction 工具)     (筛选 + 结构化抽取)       (异步写 vault)
```

**变更后**（2 段）：

```
Chat Agent  →  [显式触发]  →  Memory Writer Agent
(对话回复+构造entries)  (request_memory_extraction 工具)  (异步写 vault)
```

### 3.2 组件变更

| 组件 | 变更 |
|---|---|
| `src/everlingo/mem/agents/mem_extract_agent.py` | **删除** |
| `src/everlingo/mem/agents/mem_entries.py` | 删除 `ExtractInput` / `ExtractLLMOutput` / `LLMGeneratedEntry` / `EntryWriterProtocol`；保留 `MemoryEntry` / `ItemType` / `WhySave` |
| `src/everlingo/tools/request_memory_extract.py` | args_schema 改为 `entries: list[_MemoryEntryDraft]`；draft 仅含 LLM 字段 |
| `src/everlingo/agents/agent.py` | 删除 `_extract_agent` 实例与 `_set_pending_extract`；新增 `_pending_drafts` 累积 + `_add_pending_drafts` 回调；`ainvoke()` 末尾直接构造 MemoryEntry 入队 |
| `src/everlingo/mem/vault/templates/default/spec/memory_extract_spec.md` | **归档**至 `docs/archived/memory_extract_spec.md` |
| `docs/impl-spec/memory-extract-agent-spec.md` | **归档**至 `docs/archived/memory-extract-agent-spec.md` |
| `Memory Writer Agent` | 接口与内部流程**不变** |

### 3.3 数据流变更

**变更前**：
- Chat Agent 调 `request_memory_extraction(reason, note)` 仅设 pending 标记
- MainAgent.invoke 末尾构造 `ExtractInput` → submit 给 Extract Agent
- Extract Agent daemon thread 调 LLM 产 `entries` → `memory_writer.enqueue(entries)`

**变更后**：
- Chat Agent 在产出释义后，先 `vault_mcp_read(path="spec/memory_extract_output_spec.md")` 加载输出规范
- Chat Agent 按规范构造 entries，调 `request_memory_extraction(entries=[...])`
- 工具体把 drafts 累积到 `MainAgent._pending_drafts`
- `MainAgent.invoke()` 末尾：补全系统字段（entry_id / timestamp / 会话元数据 / new_messages / context_messages）→ `_get_memory_writer().enqueue(entries)`
- Memory Writer Agent daemon thread 异步消费，流程不变

### 3.4 system prompt 注入策略变更

**不再静态注入** `memory_extract_output_spec.md` 到 Chat Agent system prompt。

**改为按需加载**：LLM 在确定要写笔记时，自行调 `vault_mcp_read(path="spec/memory_extract_output_spec.md")` 加载输出规范与字段说明。与 `mem_writer_agent.py` 中 `read(spec/vault_spec.md)` 的模式一致。

**收益**：
- system prompt 不再依赖 vault 是否在线
- spec 升级即时生效，无需重建 agent
- token 按需：只有真要写笔记的轮次才花 token 加载 spec

**system prompt 仍保留**：
- 何时是 / 何时不是「抽取对话内容到笔记」意图（决定是否调工具，必须前置生效）
- 行为契约（调用前必须已产出知识点实际内容）
- 跳过规则（结构性，决定是否调工具，必须前置生效）
- 流程操作步骤（含「先 read spec 再调工具」约束）

> 注：system prompt 中不引入 include 概念。LLM 视角里 spec 就是普通 markdown 文件，不关心其生成过程。

## 4. 实现变更概述

### 4.1 `request_memory_extraction` 工具入参

```python
class _MemoryEntryDraft(BaseModel):
    item_type: Literal["vocab","phrase","grammar","pragmatics","others"]
    why_want_to_save_memory: Literal[
        "用户明确要求记住知识点",
        "纠正事项",
        "Chat Agent 判定",
    ]
    title: str  # 界面语言，限一句话，用于语义搜索与全文搜索

class _RequestMemoryExtractArgs(BaseModel):
    entries: list[_MemoryEntryDraft]
```

工具体：`add_drafts(entries)` 累积到 `MainAgent._pending_drafts`，返回 `"memory extraction requested"`。

### 4.2 MainAgent.invoke() 末尾

```python
if self._pending_drafts:
    drafts = self._pending_drafts
    self._pending_drafts = []
    new_messages = self._messages[self._extract_cursor:]
    context_messages = _tail_recent_turns(self._messages[:self._extract_cursor])
    self._extract_cursor = len(self._messages)
    new_text = _render_messages(new_messages)
    context_text = _render_messages(context_messages)
    ts = _now_gmt8_str()
    entries = [
        MemoryEntry(
            entry_id=str(uuid.uuid4()),
            timestamp=ts,
            chat_session_id=self._session_id,
            channel_name=self._channel_metadata.name,
            lang=self._target_lang,
            interface_language=self._profile.language.interface_language,
            new_messages=new_text,
            context_messages=context_text,
            item_type=d.item_type,
            why_want_to_save_memory=d.why_want_to_save_memory,
            title=d.title,
        )
        for d in drafts
    ]
    _get_memory_writer().enqueue(entries)
else:
    self._extract_cursor = len(self._messages)
```

`_render_messages` / `_now_gmt8_str` 从原 `mem_extract_agent.py` 搬到 `agent.py`（或 utils）。

### 4.3 累积语义

`_pending_drafts` 用 `list` 顺序追加。支持一次 invoke 中多次调用 `request_memory_extraction`（例如先解释一个词、再纠正一个语法点），每次调用的 drafts 顺序累积，invoke 末尾一次性入队。

### 4.4 Chat Agent system prompt 改写要点

`### 抽取对话内容到笔记` 节四个子节：

- **何时是 抽取对话内容到笔记 意图**：按 `why_want_to_save_memory` 字段值分类
  - 用户明确要求记住 → `"用户明确要求记住知识点"`
  - 纠正事项 → `"纠正事项"`
  - 其他值得记录 → `"Chat Agent 判定"`
- **何时不是 抽取对话内容到笔记 意图**：与目标学习语言无关的闲聊 / 纯查词翻译无纠正 / 用户偏好类（应入 USER.md）/ 琐碎显而易见 / 单条 Message 文本超过 1000 字不作为事实来源
- **执行 抽取对话内容到笔记 前必须**：已在本轮回复中产出该知识点的实际内容（释义/解释/用法/举例）。这是下游 Memory Writer Agent 生成 conversation_context 与笔记正文的唯一事实来源。保留原错误示例与正确示例。
- **当需要执行 抽取对话内容到笔记 时，按以下流程操作**：
  1. 先调用 `vault_mcp_read(path="spec/memory_extract_output_spec.md")` 加载 entries 输出规范与字段说明
  2. 按规范构造 entries，调用 `request_memory_extraction(entries=[...])`
  3. 回复用户：已提交后台笔记请求
  4. 下游 Memory Writer Agent 会异步将 entries 写入笔记库

### 4.5 测试

- **删除** `tests/test_mem_extract_agent.py`
- **修改** `tests/test_main_agent.py`：
  - 删除 `patch("everlingo.agents.agent.MemoryExtractAgent")`
  - 改 mock `_get_memory_writer().enqueue`
  - 用例：不触发 / 触发 1 entry / 一次 invoke 触发 2 entries（累积）/ 跨 invoke 游标正确
- **不动** `tests/test_mem_writer_agent.py`

### 4.6 文档同步

- `docs/impl-spec/chat-agent-spec.md`：数据流水线图改 2 段；Memory Extract 节重写为「记忆抽取触发」
- `docs/impl-spec/memory-writer-agent-spec.md`：上游来源由 Extract Agent 改为 Chat Agent
- `docs/impl-spec/chat-agent-tools-spec.md`：`request_memory_extraction` args 改为 entries 列表；调用准则提示「调用前应先 `vault_mcp_read(path="spec/memory_extract_output_spec.md")` 了解字段结构与含义」
- `TASKS.md`：新增条目记录本次架构变更

## 5. 决策

采用本方案。

- **架构层面**：删除 Memory Extract Agent，流水线降为 2 段
- **接口层面**：`request_memory_extraction` 工具入参改为 `entries: list`，系统字段由 MainAgent 代码补全
- **spec 加载**：从静态注入 system prompt 改为 LLM 按需 `vault_mcp_read`
- **累积语义**：`_pending_drafts` 支持一轮多次工具调用累积
- **归档**：原 Extract Agent 相关 spec 与设计文档归档至 `docs/archived/`，保留历史溯源
