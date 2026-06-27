我的建议很明确：

> **不要做一个“大而全 Agent”。**  
> 应该拆成 **用户聊天 Agent** 和 **知识库记忆 Agent / 服务** 两个子领域。  
> 但也不要让两个 Agent 像人一样“自由聊天”。更推荐用 **事件 + 结构化 Memory Ops + 可验证写入器** 交互。

也就是说：

```text
Chatbot Agent 负责“教”
Memory Agent 负责“整理”
Retriever 负责“查”
Writer 负责“安全写文件”
Orchestrator / Gateway 负责“调度”
```

最适合「记了么」的形态是：

> **前台同步查询，后台异步维护。**

---

# 结论先说

推荐架构：

```text
用户消息
  ↓
Gateway / Session Orchestrator
  ↓
同步读取 USER.md + 检索 Markdown 知识库
  ↓
Chat Tutor Agent 生成用户可见回答
  ↓
立即返回给用户
  ↓
异步投递 Memory Update Job
  ↓
Memory Curator Agent 提取记忆更新
  ↓
Memory Writer 校验并写入 Markdown
  ↓
Indexer 更新 SQLite / Vector Index
  ↓
Wiki 异步刷新
```

一句话：

> **聊天 Agent 不直接维护知识库；它只使用知识库。  
> 知识库由专门的 Memory Agent / Memory Service 异步维护。**

---

# 为什么不建议一个大 Agent 全包？

一个大 Agent 同时负责：

- 理解用户问题；
- 教外语；
- 读取用户画像；
- 检索旧记忆；
- 判断哪些要记；
- 修改 Markdown；
- 合并重复词条；
- 更新复习计划；
- 维护 Wiki；
- 生成最终回答；

看起来简单，但长期会有很多问题。

## 主要问题

| 问题 | 说明 |
|---|---|
| Prompt 变胖 | 教学规则、记忆规则、文件规则、复习规则全部塞进一个 system prompt，难维护 |
| 响应变慢 | 用户只是问一个词，却要等它思考怎么写库、怎么合并、怎么排复习 |
| 副作用不可控 | 用户聊天过程中模型可能误改、乱改、重复写 Markdown |
| 难测试 | 回答质量和知识库维护质量耦合在一起，出了问题不好定位 |
| 难升级 | 以后复习算法、浏览器插件、错题集、Wiki 重建都会污染聊天逻辑 |
| 难审计 | 你很难知道“为什么这次回答顺手改了这个文件” |
| 成本高 | 每次用户聊天都带着维护知识库的重逻辑跑一遍 |

尤其你的产品核心是 **长期记忆**，不是一次性聊天。长期记忆的正确性、可追踪性、可回滚性，比“让一个 Agent 很聪明”更重要。

所以更推荐：

> **把 Agent 的“认知能力”和系统的“状态修改能力”分开。**

---

# 推荐的 Agent 分工

## 1. Chat Tutor Agent

这是用户直接面对的小记。

它负责：

- 回答查词、翻译、语法、表达问题；
- 根据用户画像调整解释风格；
- 使用同步检索出来的相关记忆；
- 在回答中适度提醒“你之前也查过这个”；
- 给出学习建议；
- 可输出轻量的 `memory_candidate`，但不直接写文件。

它的 system prompt 应该关注：

```text
你是一个有记忆的 AI 外语老师。
你需要根据用户画像、相关记忆、当前问题给出教学回答。
不要直接修改知识库。
如果发现值得记录的内容，可以在内部结果中给出 memory_candidates。
```

它的输入大概是：

```text
USER.md 摘要
当前会话上下文
同步检索到的相关词条 / 语法 / 错题
今日到期复习项摘要
用户当前消息
```

它的输出可以是：

```json
{
  "answer": "用户可见回答……",
  "memory_candidates": [
    {
      "kind": "vocab",
      "lang": "ja",
      "headword": "曖昧",
      "reason": "用户查询了词义，并且这个词容易和中文暧昧混淆"
    }
  ]
}
```

但即使没有 `memory_candidates`，后台 Memory Agent 也可以自己从对话事件里提取。

---

## 2. Memory Curator Agent

这是后台知识库整理员。

它不和用户直接聊天。

它负责：

- 从用户问题、助手回答、网页上下文中提取值得记忆的内容；
- 判断是词汇、短语、语法、错题、用户偏好，还是上下文事件；
- 判断是否已有重复词条；
- 生成结构化 `MemoryOps`；
- 不直接写 Markdown。

它的 system prompt 应该关注：

```text
你是 EverLingo 的知识库整理 Agent。
你的任务是从对话事件中提取长期学习记忆。
只输出符合 JSON Schema 的 MemoryOps。
不要生成用户可见回答。
不要编造用户没有表达过的偏好。
不要直接输出 Markdown 文件内容，除非 MemoryOps 要求。
```

输出示例：

```json
{
  "ops": [
    {
      "type": "upsert_vocab",
      "lang": "ja",
      "headword": "曖昧",
      "reading": "あいまい",
      "summary": "表示不明确、含糊、模棱两可。日语中使用范围比中文“暧昧”更广。",
      "tags": ["ja", "vocab", "confusing"],
      "source_event_id": "01JZEVT123"
    },
    {
      "type": "increment_seen_count",
      "lang": "ja",
      "headword": "曖昧"
    },
    {
      "type": "create_review_card",
      "lang": "ja",
      "target_headword": "曖昧",
      "card_type": "meaning"
    }
  ]
}
```

---

## 3. Memory Writer

这个最好不是 Agent，而是普通程序。

它负责：

- 校验 `MemoryOps`；
- 查找已有 Markdown 文件；
- 合并 frontmatter；
- 更新 `seen_count`、`last_seen`、`due_at`；
- 追加 encounter log；
- 创建新 Markdown 文件；
- 防止路径穿越、重复写入、非法字段；
- 写入后触发索引更新。

也就是说：

> **LLM 决定“应该怎么整理”，程序决定“能不能这样写、具体怎么写”。**

这是非常重要的边界。

---

## 4. Memory Retriever

这个也不一定是 Agent，更适合做成服务。

它负责：

- 根据用户输入查 Markdown 知识库；
- 用 SQLite FTS 查关键词；
- 用向量索引查语义相似；
- 用 alias 查已有词条；
- 根据语言、类型、最近使用时间、掌握度排序；
- 返回 Top K 相关记忆片段。

输入：

```json
{
  "query": "曖昧 是什么意思？",
  "lang_hint": "ja",
  "user_id": "default",
  "top_k": 8
}
```

输出：

```json
{
  "memories": [
    {
      "id": "01JZABD123",
      "type": "vocab",
      "lang": "ja",
      "title": "曖昧",
      "path": "items/ja/vocab/aimai--01JZABD123.md",
      "score": 0.91,
      "snippet": "曖昧 表示不明确、含糊、模棱两可……"
    }
  ]
}
```

可以有一个很轻的 **Query Rewriter Agent**，专门把用户问题改写成检索 query，但不是必需。

---

# 同步查询，异步维护

你提到的“知识库异步，查询时同步”，我认为是正确方向。

## 同步部分

用户发消息时，必须同步做这些事：

```text
1. 读取 USER.md / 用户画像
2. 检索相关 Markdown 记忆
3. 把相关记忆注入 Chat Agent
4. 生成回答
5. 返回用户
```

因为这直接影响回答质量。

例如用户问：

```text
曖昧 是什么意思？
```

如果知识库里已经有：

```text
你之前查过曖昧，容易和中文“暧昧”混淆。
```

那么 Chat Agent 应该立刻知道，并回答：

```text
你之前也查过这个词。这里再帮你巩固一下：
日语的「曖昧」比中文“暧昧”更广，主要是“不明确、含糊”的意思……
```

这是产品体验的核心。

---

## 异步部分

回答用户之后，再异步做：

```text
1. 保存原始事件
2. 提取记忆
3. 合并词条
4. 生成复习卡
5. 更新 Markdown
6. 重建索引
7. 刷新 Wiki
```

这样用户不会等。

---

# 推荐请求流程

可以这样设计一次对话流程：

```text
User Message
  ↓
Session Orchestrator
  ↓
append raw event to events/inbox
  ↓
Memory Retriever 同步检索
  ↓
Chat Tutor Agent 生成回答
  ↓
Return Answer
  ↓
enqueue MemoryUpdateJob
  ↓
Memory Curator Agent 生成 MemoryOps
  ↓
Memory Writer 写 Markdown
  ↓
Indexer 更新索引
  ↓
Wiki Builder 异步刷新
```

用伪代码表示：

```python
async def handle_user_message(session_id: str, message: str) -> str:
    session = await session_store.get(session_id)

    user_profile = memory_store.load_user_profile(session.user_id)

    retrieved_memories = await memory_retriever.search(
        user_id=session.user_id,
        query=message,
        lang_hint=session.lang_hint,
        top_k=8,
    )

    answer_result = await chat_tutor_agent.run(
        user_message=message,
        user_profile=user_profile,
        session_context=session.recent_messages,
        retrieved_memories=retrieved_memories,
    )

    await channel.send(session.channel_id, answer_result.answer)

    event = await event_store.append_chat_event(
        session_id=session_id,
        user_message=message,
        assistant_answer=answer_result.answer,
        retrieved_memory_ids=[m.id for m in retrieved_memories],
        memory_candidates=answer_result.memory_candidates,
    )

    await job_queue.enqueue(
        "memory_update",
        {
            "user_id": session.user_id,
            "event_id": event.id,
        },
    )

    return answer_result.answer
```

后台任务：

```python
async def process_memory_update_job(job: dict) -> None:
    event = await event_store.load(job["event_id"])

    existing_candidates = await memory_retriever.search(
        user_id=job["user_id"],
        query=event.user_message,
        top_k=12,
    )

    ops = await memory_curator_agent.extract_ops(
        event=event,
        existing_memories=existing_candidates,
    )

    validated_ops = memory_ops_validator.validate(ops)

    changed_files = await memory_writer.apply_ops(
        user_id=job["user_id"],
        ops=validated_ops,
    )

    await memory_indexer.update_files(
        user_id=job["user_id"],
        files=changed_files,
    )

    await wiki_builder.schedule_rebuild(user_id=job["user_id"])
```

---

# 两个 Agent 是否要“互相对话”？

我的建议是：

> **不要让 Chat Agent 和 Memory Agent 自由对话。**  
> 它们应该通过结构化事件和结构化操作交互。

也就是说，不要这样：

```text
Chat Agent：我刚回答了曖昧，你看看要不要记？
Memory Agent：好的，我觉得应该记，还要加复习卡。
Chat Agent：那你怎么写？
Memory Agent：我这样写……
```

这种方式不可控、难测试、难重放。

更推荐：

```text
Chat Agent 输出 answer + memory_candidates
Event Store 保存完整事件
Memory Agent 读取事件，输出 JSON MemoryOps
Memory Writer 校验并执行
```

这叫 **typed boundary**，也就是用明确的数据结构隔离 Agent。

---

# 什么时候需要同步写知识库？

虽然总体建议异步，但有几类情况可以同步或半同步处理。

## 1. 用户明确修改偏好

例如用户说：

```text
以后解释日语时请都标注假名。
```

这个最好尽快更新 `USER.md`，因为下一轮就要生效。

可以有两种做法。

### 做法 A：快速同步写

如果判断是明确偏好，可以同步更新：

```text
用户消息
  ↓
Preference Detector
  ↓
更新 USER.md
  ↓
Chat Agent 回答：“好的，我会记住。”
```

### 做法 B：高优先级异步写

先回答：

```text
好的，我会记住。以后解释日语时我会标注假名。
```

然后立即投递高优先级任务，通常几百毫秒到几秒内完成。

我更推荐：

> **偏好更新走高优先级异步，必要时当前 Session 也临时写入 session memory。**

也就是说，就算 `USER.md` 还没落盘，当前会话也能立刻生效。

---

## 2. 用户命令式修改知识库

例如：

```text
把 USER.md 里“目标语言”改成日语和英语。
```

或者：

```text
把曖昧这条笔记删掉。
```

这类属于显式操作，可以同步确认：

```text
你确定要删除「曖昧」这条学习笔记吗？
```

确认后再执行。

---

## 3. 复习打分

例如：

```text
这个我记住了。
这个我又忘了。
太简单了。
```

这类会影响 `mastery` 和 `due_at`，可以同步更新 SQLite 调度状态，Markdown 摘要稍后异步同步。

---

# 最佳架构形态

我建议你把系统拆成这几层：

```text
Channel Layer
  WeChat / Web / TUI / Browser Extension

Gateway / Session Layer
  Session 管理、用户识别、多端路由

Orchestration Layer
  调用 Retriever、Chat Agent、Job Queue

Agent Layer
  Chat Tutor Agent
  Memory Curator Agent
  Review Coach Agent，可后加
  Query Rewriter Agent，可选

Memory Service Layer
  MemoryStore
  MemoryRetriever
  MemoryWriter
  MemoryIndexer
  WikiBuilder

Storage Layer
  Markdown Vault
  SQLite FTS
  Vector Index
  Event Log
```

图示：

```text
             ┌────────────────────┐
             │ WeChat / Web / TUI │
             └─────────┬──────────┘
                       │
                       ▼
             ┌────────────────────┐
             │ Gateway / Session  │
             └─────────┬──────────┘
                       │
                       ▼
             ┌────────────────────┐
             │ Orchestrator       │
             └──────┬───────┬─────┘
                    │       │
       sync read    │       │ async job
                    │       ▼
                    │  ┌────────────────────┐
                    │  │ Memory Curator     │
                    │  │ Agent              │
                    │  └─────────┬──────────┘
                    │            ▼
                    │  ┌────────────────────┐
                    │  │ Memory Writer      │
                    │  └─────────┬──────────┘
                    │            ▼
                    │  ┌────────────────────┐
                    │  │ Markdown Vault     │
                    │  └─────────┬──────────┘
                    │            ▼
                    │  ┌────────────────────┐
                    │  │ Indexer / Wiki     │
                    │  └────────────────────┘
                    │
                    ▼
          ┌────────────────────┐
          │ Memory Retriever   │
          └─────────┬──────────┘
                    ▼
          ┌────────────────────┐
          │ Chat Tutor Agent   │
          └────────────────────┘
```

---

# System Prompt 应该怎么拆

## Chat Tutor Agent Prompt

重点是教学体验。

```text
你是 EverLingo，一个有记忆的 AI 外语老师。

你的目标：
- 用用户能理解的方式解释外语问题；
- 根据用户画像调整例句、难度、语气；
- 使用提供的相关记忆，但不要编造没有提供的记忆；
- 如果用户重复查询，温和提醒并帮助巩固；
- 不要直接修改知识库；
- 如果发现可能值得记录的内容，可以输出 memory_candidates。
```

它看到的是经过检索后的内容：

```text
<USER_PROFILE>
...
</USER_PROFILE>

<RELEVANT_MEMORIES>
...
</RELEVANT_MEMORIES>

<DUE_REVIEWS>
...
</DUE_REVIEWS>
```

---

## Memory Curator Agent Prompt

重点是结构化整理。

```text
你是 EverLingo 的知识库整理 Agent。

你的任务：
- 从对话事件中提取长期有价值的学习记忆；
- 识别词汇、短语、语法、错题、用户偏好、上下文；
- 判断是否应更新已有记忆；
- 输出 JSON MemoryOps；
- 不要生成用户可见回复；
- 不要编造用户背景；
- 不要直接写文件路径，除非已有候选项给出；
- 不要删除内容，除非用户明确要求。
```

输出只允许：

```json
{
  "ops": []
}
```

---

## Memory Writer 不用 Prompt

它不是 Agent。

它应该是代码：

```text
validate_ops()
resolve_target_file()
merge_frontmatter()
append_encounter()
write_markdown()
update_index()
```

这个边界越硬，系统越稳。

---

# 一个大 Agent 什么时候可以接受？

早期原型阶段可以接受一个大 Agent，但我建议只是临时方案。

比如 MVP 可以这样：

```text
Chat Agent
  - 回答用户
  - 输出 memory_ops
MemoryWriter
  - 写 Markdown
```

也就是说，即使只有一个 LLM，也要在输出结构上分离：

```json
{
  "answer": "用户可见回答",
  "memory_ops": []
}
```

但是不要长期让它直接调用文件工具随便写。

如果项目进入多端、复习、浏览器插件阶段，就应该拆开。

---

# 我建议的演进路线

## 阶段一：单 Agent，双输出

适合最快跑通。

```text
Chat Agent 输出：
- answer
- memory_ops
```

但文件写入仍由程序执行。

优点：

- 实现快；
- 逻辑少；
- 方便验证产品体验。

缺点：

- 聊天和记忆提取耦合；
- prompt 会逐渐变重。

---

## 阶段二：双 Agent，异步记忆

这是我认为你当前最适合的目标架构。

```text
Chat Tutor Agent
  只负责回答

Memory Curator Agent
  后台异步整理

Memory Writer
  程序写 Markdown
```

优点：

- 用户响应快；
- 知识库维护稳定；
- 容易调试；
- 适合未来扩展。

---

## 阶段三：多个专业 Agent

等功能变多后再拆：

```text
Chat Tutor Agent
Memory Curator Agent
Review Coach Agent
Writing Correction Agent
Browser Reading Agent
Profile Manager Agent
```

但不要太早拆。

过早拆太多 Agent，会增加编排复杂度。

---

# 推荐你现在落地的版本

结合你现在的 EverLingo 架构，我建议当前实现成：

```text
Chat Agent 1 个
Memory Curator Agent 1 个
Memory Service 若干普通类
```

具体模块：

```text
everlingo/
  agent/
    chat_tutor_agent.py
    memory_curator_agent.py

  memory/
    store.py
    retriever.py
    writer.py
    indexer.py
    schemas.py
    ops.py

  gateway/
    gateway.py
    session.py

  jobs/
    queue.py
    workers.py
```

核心类：

```text
ChatTutorAgent
MemoryCuratorAgent
MemoryStore
MemoryRetriever
MemoryWriter
MemoryIndexer
MemoryUpdateWorker
```

---

# 最重要的设计原则

## 1. Agent 不直接写文件

Agent 输出意图：

```json
{
  "type": "upsert_vocab",
  "headword": "曖昧"
}
```

程序执行写入。

---

## 2. Retrieval 同步，Curation 异步

```text
同步：为了让回答更懂用户
异步：为了不拖慢聊天体验
```

---

## 3. Markdown 是 Source of Truth

索引可以重建。

```text
Markdown Vault = 真数据
SQLite FTS = 检索缓存
Vector Index = 语义缓存
MkDocs = 浏览视图
```

---

## 4. 通过事件连接 Agent

不要让 Agent 自由互聊。

```text
ChatEvent
MemoryUpdateJob
MemoryOps
```

这是可测试、可重放、可审计的。

---

## 5. 显式用户偏好优先处理

用户说：

```text
以后都用技术文档例句解释。
```

这种可以高优先级更新 `USER.md`，并立即影响当前 session。

---

# 最终建议

我会这样定架构：

```text
一个用户面对的 Chat Tutor Agent
一个后台 Memory Curator Agent
一个同步 Memory Retriever
一个确定性的 Memory Writer
一个异步 Indexer / Wiki Builder
```

不要做一个大 Agent。

最核心的一句话是：

> **Chat Agent 负责“当下教得好”，Memory Agent 负责“长期记得准”。**

这和「记了么」的产品定位是匹配的：

- 用户体验上，它像一个自然聊天的 AI 外语老师；
- 系统内部，它又像一个严谨的 Markdown 知识库维护器；
- 两者通过结构化事件和 Memory Ops 连接；
- 查询同步，更新异步；
- 最终沉淀成可浏览、可编辑、可复习的 Wiki。