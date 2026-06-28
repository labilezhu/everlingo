下面是我建议给「记了么 EverLingo」采用的 **Agent 记忆结构技术选型**。

一句话结论：

> **用 Markdown Vault 作为记忆的 Source of Truth，用 YAML Frontmatter 做机器可读元数据，用目录结构组织知识，用 SQLite FTS / Vector Index 做可重建索引，用 MkDocs Material 暴露成浏览器 Wiki。**

这套方案最适合你这个产品的当前阶段：**开源、轻量、可读、可编辑、Agent 友好、浏览器可浏览、未来可扩展到复习系统和浏览器插件。**

---

# 推荐方案总览

## 核心选型

| 层 | 推荐技术 | 作用 |
|---|---|---|
| 记忆源文件 | Markdown 文件 | 人类可读、Git 友好、Agent 易写 |
| 元数据 | YAML Frontmatter | 机器可读，方便检索、过滤、复习调度 |
| 目录结构 | Obsidian / Wiki 风格 Vault | 组织用户记忆、词汇、语法、上下文、错题 |
| 浏览器 Wiki | MkDocs Material | 静态 Wiki，搜索、目录、标签、移动端友好 |
| 全文搜索 | SQLite FTS5 | 快速查词、查上下文、查笔记 |
| 语义检索 | SQLite + `sqlite-vec` / Chroma / FAISS | 根据当前对话召回相关记忆 |
| 复习调度 | Markdown Frontmatter 或 SQLite sidecar | 间隔重复、掌握度、下次复习时间 |
| Agent 写入机制 | Structured Memory Ops | Agent 不直接乱改文件，而是生成结构化操作 |
| 同步 / 版本 | Git 可选 | 用户可备份、回滚、审计 |

---

# 最适合的总体架构

建议采用：

```text
Markdown Memory Vault
        ↓
Frontmatter Parser
        ↓
SQLite FTS / Vector Index
        ↓
Retrieval Layer
        ↓
Agent Context Injection
        ↓
Memory Ops Writer
        ↓
MkDocs Wiki Browser
```

核心原则：

> **Markdown 是唯一可信数据源。SQLite / 向量索引只是缓存，可以随时重建。**

这样可以避免一开始就被数据库 schema 锁死，同时保留将来做高性能检索和统计分析的能力。

---

# 推荐目录结构

建议每个用户一个独立 Memory Vault。

```text
data/
  users/
    default/
      memory/
        README.md
        USER.md
        INDEX.md

        profile/
          preferences.md
          goals.md
          background.md
          learning-style.md

        inbox/
          2026-06-26.md

        events/
          2026/
            06/
              2026-06-26.md

        items/
          en/
            vocab/
              gcc--01JZABC123.md
              ambiguous--01JZABC456.md
            phrases/
              take-for-granted--01JZABC789.md
            grammar/
              present-perfect--01JZABD001.md

          ja/
            vocab/
              aimai--01JZABD123.md
              yoroshiku--01JZABD456.md
            phrases/
              yoroshiku-onegaishimasu--01JZABD789.md
            grammar/
              te-form--01JZABE001.md

          fr/
            vocab/
            phrases/
            grammar/

          de/
            vocab/
            phrases/
            grammar/

        contexts/
          web/
            2026/
              06/
                2026-06-26-react-docs.md
          chat/
            2026/
              06/
                2026-06-26-wechat.md
          reading/
            ja/
              nhk-easy-2026-06-26.md

        mistakes/
          ja/
            particle-wa-ga--01JZABF001.md
          en/
            article-a-the--01JZABF002.md

        review/
          cards/
            ja/
              aimai--recognition--01JZABG001.md
              aimai--production--01JZABG002.md
          sessions/
            2026-06-26.md
          due.md

        relations/
          aliases.md
          redirects.md
          tags.md

        agent/
          memory-policy.md
          extraction-rules.md
          prompt-snippets.md

      index/
        memory.sqlite
        embeddings.sqlite
```

---

# 关键文件说明

## `USER.md`

你现在已经有 `USER.md`，建议保留它作为最高优先级的用户画像文件。

```markdown
---
id: user-default
type: user_profile
updated_at: 2026-06-26T10:30:00+08:00
schema_version: 1
---

# 用户画像

## 基本背景

- 母语：简体中文
- 目标语言：日本語、英语
- 职业背景：后端开发 / 技术学习
- 常见场景：阅读技术文档、职场沟通、辅导孩子学习

## 回答偏好

- 喜欢结构化解释
- 希望多给上下文例句
- 学日语时希望标注假名、语气、使用场景
- 学英语时希望结合技术文档语境

## 记忆偏好

- 反复查询的词汇需要加入复习
- 对容易混淆的表达需要生成对比笔记
- 错题和误用要单独归类
```

这个文件适合直接注入 system prompt，因为它短、稳定、全局有效。

---

## 词汇记忆文件

例如：

```text
items/ja/vocab/aimai--01JZABD123.md
```

内容：

```markdown
---
id: 01JZABD123
type: vocab
lang: ja
headword: 曖昧
reading: あいまい
aliases:
  - あいまい
  - ambiguous
tags:
  - ja
  - vocab
  - adjective
  - confusing
status: learning
mastery: 0.42
first_seen: 2026-06-22T18:08:00+08:00
last_seen: 2026-06-26T09:15:00+08:00
seen_count: 4
due_at: 2026-06-28T09:00:00+08:00
source_contexts:
  - ../../contexts/chat/2026/06/2026-06-22-wechat.md
  - ../../contexts/reading/ja/nhk-easy-2026-06-26.md
related:
  - 明確
  - はっきり
  - 微妙
schema_version: 1
---

# 曖昧

## 给我的解释

`曖昧` 表示“不清楚、不明确、模棱两可”。

它既可以描述语言表达不清楚，也可以描述态度、关系、边界不明确。

## 常见用法

| 表达 | 含义 |
|---|---|
| 曖昧な返事 | 含糊的回答 |
| 曖昧な関係 | 暧昧的关系 |
| 意味が曖昧 | 意思不明确 |

## 例句

> 彼の返事は曖昧だった。  
> 他的回答很含糊。

> この文章の意味は少し曖昧です。  
> 这篇文章的意思有点不明确。

## 我容易混淆的点

`曖昧` 不完全等于中文里的“暧昧”。

中文“暧昧”经常偏感情关系；日语 `曖昧` 更广，可以表示任何“不明确”。

## 记忆钩子

可以理解为：

> 边界没有画清楚。

## 遇到记录

- 2026-06-22：微信中询问“曖昧”和中文“暧昧”的区别。
- 2026-06-26：阅读日语文章时再次遇到。
```

---

## 短语文件

```text
items/en/phrases/take-for-granted--01JZABC789.md
```

```markdown
---
id: 01JZABC789
type: phrase
lang: en
headword: take for granted
aliases:
  - taken for granted
tags:
  - en
  - phrase
  - workplace
status: learning
mastery: 0.35
first_seen: 2026-06-20T21:00:00+08:00
last_seen: 2026-06-26T08:30:00+08:00
seen_count: 3
due_at: 2026-06-27T09:00:00+08:00
schema_version: 1
---

# take for granted

## 含义

`take something for granted` 表示：

1. 认为某事理所当然；
2. 没有意识到某事的价值；
3. 默认某事一定成立。

## 技术场景例句

> We shouldn't take backward compatibility for granted.

不要想当然地认为向后兼容一定存在。

## 常见错误

不要直译成：

> take it as granted

更自然的是：

> take it for granted
```

---

## 语法点文件

```text
items/ja/grammar/te-form--01JZABE001.md
```

```markdown
---
id: 01JZABE001
type: grammar
lang: ja
title: て形
tags:
  - ja
  - grammar
  - verb
status: learning
mastery: 0.25
first_seen: 2026-06-24T10:00:00+08:00
last_seen: 2026-06-26T10:10:00+08:00
due_at: 2026-06-27T09:00:00+08:00
schema_version: 1
---

# て形

## 是什么

`て形` 是日语动词的一种连接形式，常用于连接动作、请求、状态持续等。

## 常见用途

| 用法 | 例子 | 含义 |
|---|---|---|
| 请求 | 見てください | 请看 |
| 连接动作 | 朝ご飯を食べて、学校へ行く | 吃早饭后去学校 |
| 进行状态 | 本を読んでいる | 正在读书 |

## 我当前的问题

- 五段动词变形还不熟。
- `ている` 的“正在”和“结果状态”容易混。
```

---

## 上下文文件

浏览器插件、微信、Web Chat 都应该把真实上下文保存下来。

```text
contexts/web/2026/06/2026-06-26-react-docs.md
```

```markdown
---
id: 01JZCTX123
type: context
source_type: web
url: https://react.dev/reference/react/useMemo
title: React useMemo Reference
lang: en
captured_at: 2026-06-26T11:20:00+08:00
related_items:
  - ../../items/en/vocab/memoization--01JZABC222.md
  - ../../items/en/phrases/skip-recalculation--01JZABC333.md
schema_version: 1
---

# React useMemo Reference

## 原文片段

> React will skip recalculating the cached value if none of the dependencies have changed.

## 用户查询

用户划词查询：

> skip recalculating

## 当时解释摘要

这里的 `skip recalculating` 表示“跳过重新计算”。

在技术文档语境中，`skip` 常表示“不执行某个步骤”，不是“跳过阅读”的意思。
```

这个很关键，因为你的产品卖点不是“查词”，而是：

> **把查询行为本身变成学习资产。**

上下文文件就是这个资产的原始证据。

---

## 错题 / 误用文件

这个对你提到的“初中娃错题集”也很适合。

```text
mistakes/en/article-a-the--01JZABF002.md
```

```markdown
---
id: 01JZABF002
type: mistake
lang: en
title: 冠词 a / the 混淆
tags:
  - en
  - mistake
  - grammar
  - article
status: active
mastery: 0.2
first_seen: 2026-06-26T19:30:00+08:00
last_seen: 2026-06-26T19:30:00+08:00
due_at: 2026-06-27T19:30:00+08:00
related_items:
  - ../../items/en/grammar/articles--01JZART001.md
schema_version: 1
---

# 冠词 a / the 混淆

## 原句

> I saw dog in park.

## 修正

> I saw a dog in the park.

## 错因

- `dog` 是第一次提到的可数名词单数，需要 `a`。
- `park` 是说话双方都知道的具体地点，用 `the park` 更自然。

## 强化练习

请补全：

1. I bought ___ book yesterday.
2. ___ book is about programming.
```

---

# Markdown Frontmatter 字段规范

建议先定义一个轻量 schema，避免后面文件越来越乱。

## 通用字段

```yaml
id: 01JZABD123
type: vocab
lang: ja
title: 曖昧
tags:
  - ja
  - vocab
status: learning
created_at: 2026-06-26T10:00:00+08:00
updated_at: 2026-06-26T10:30:00+08:00
schema_version: 1
```

## 学习类字段

```yaml
mastery: 0.42
first_seen: 2026-06-22T18:08:00+08:00
last_seen: 2026-06-26T09:15:00+08:00
seen_count: 4
due_at: 2026-06-28T09:00:00+08:00
ease: 2.3
interval_days: 2
lapses: 1
```

## 关联字段

```yaml
aliases:
  - あいまい
  - ambiguous
source_contexts:
  - ../../contexts/chat/2026/06/2026-06-22-wechat.md
related:
  - 明確
  - はっきり
  - 微妙
```

---

# Agent 记忆分层设计

建议不要把所有记忆都叫 memory，而是分层。

## 1. Profile Memory

稳定用户画像。

位置：

```text
USER.md
profile/preferences.md
profile/goals.md
profile/background.md
```

用途：

- 注入 system prompt；
- 决定解释风格；
- 决定学习目标；
- 决定例句领域。

示例：

```markdown
用户是后端开发者，英语主要用于阅读技术文档，日语处于初级阶段。
```

---

## 2. Episodic Memory

事件记忆，也就是“什么时候发生过什么”。

位置：

```text
events/2026/06/2026-06-26.md
contexts/chat/2026/06/2026-06-26-wechat.md
contexts/web/2026/06/2026-06-26-react-docs.md
```

用途：

- 保留学习场景；
- 支持回溯；
- 支持“你上次问过这个词”；
- 支持生成学习周报。

---

## 3. Semantic Learning Memory

真正沉淀下来的知识点。

位置：

```text
items/{lang}/vocab/
items/{lang}/phrases/
items/{lang}/grammar/
mistakes/
```

用途：

- 词汇；
- 短语；
- 语法；
- 易错点；
- 表达对比。

这是 Wiki 的主体。

---

## 4. Review Memory

复习调度记忆。

位置：

```text
review/cards/
review/sessions/
review/due.md
```

用途：

- 记录掌握度；
- 安排复习；
- 生成测验；
- 主动推送。

---

## 5. Procedural Memory

Agent 行为规则。

位置：

```text
agent/memory-policy.md
agent/extraction-rules.md
agent/prompt-snippets.md
```

用途：

- 什么需要记；
- 什么不需要记；
- 如何合并重复词条；
- 如何生成复习卡片；
- 如何更新 `USER.md`。

---

# Agent 写入记忆的方式

不建议让 LLM 直接编辑 Markdown 文件。

更推荐：

> **LLM 只输出结构化 Memory Ops，程序负责验证、合并、写入文件。**

例如 Agent 输出：

```json
{
  "ops": [
    {
      "type": "upsert_item",
      "item_type": "vocab",
      "lang": "ja",
      "headword": "曖昧",
      "reading": "あいまい",
      "aliases": ["あいまい", "ambiguous"],
      "tags": ["ja", "vocab", "confusing"],
      "summary": "表示不明确、含糊、边界不清。日语中比中文“暧昧”使用范围更广。",
      "source_context_id": "01JZCTX123"
    },
    {
      "type": "increment_seen_count",
      "target": "曖昧",
      "lang": "ja"
    },
    {
      "type": "create_review_card",
      "target": "曖昧",
      "card_type": "recognition"
    }
  ]
}
```

然后 Python 代码负责：

1. 查找是否已有词条；
2. 判断是否合并；
3. 更新 frontmatter；
4. 追加 encounter log；
5. 更新索引；
6. 生成或更新复习卡片。

这样会稳定很多。

---

# 检索与注入策略

不要每次都把整个 Wiki 注入 Agent。

建议每次对话注入：

```text
1. USER.md
2. 当前会话摘要
3. 最近若干条事件
4. 与当前输入最相关的 vocab / phrase / grammar / mistake
5. 今日 due 的复习项目摘要
```

推荐检索流程：

```text
用户输入
  ↓
语言识别 / 意图识别
  ↓
关键词检索：SQLite FTS5
  ↓
语义检索：Vector Index
  ↓
根据 type / lang / recency / mastery 加权排序
  ↓
取 Top K Markdown 片段
  ↓
注入 Agent Context
```

召回优先级建议：

| 情况 | 优先召回 |
|---|---|
| 用户查词 | 同 headword、alias、同语言词条 |
| 用户翻译 | phrase、grammar、user preference |
| 用户问语法 | grammar、mistakes |
| 用户说“我又忘了” | review cards、mistakes |
| 用户阅读网页 | contexts、相关 vocab、phrases |
| 用户问“我最近学了什么” | events、review sessions |

---

# 浏览器 Wiki 选型

## 首选：MkDocs Material

我建议你直接用 **MkDocs Material**。

理由：

- Python 项目天然适配；
- 配置简单；
- Markdown 原生；
- 支持目录、搜索、标签、代码块、表格；
- 移动端体验好；
- 可以由 FastAPI 直接托管静态文件；
- GitHub Pages 也能部署；
- 很适合作为“学习 Wiki”。

安装：

```bash
uv add mkdocs mkdocs-material mkdocs-awesome-pages-plugin mkdocs-roamlinks-plugin
```

或者：

```bash
pip install mkdocs mkdocs-material mkdocs-awesome-pages-plugin mkdocs-roamlinks-plugin
```

---

## `mkdocs.yml` 示例

```yaml
site_name: EverLingo Memory Wiki
site_description: 有记忆的 AI 外语老师
site_url: http://localhost:8000/wiki/

docs_dir: data/users/default/memory
site_dir: web/dist/wiki

theme:
  name: material
  language: zh
  features:
    - navigation.tabs
    - navigation.sections
    - navigation.expand
    - navigation.indexes
    - navigation.top
    - search.highlight
    - search.suggest
    - content.code.copy

plugins:
  - search
  - awesome-pages
  - roamlinks

markdown_extensions:
  - admonition
  - tables
  - toc:
      permalink: true
  - footnotes
  - attr_list
  - pymdownx.details
  - pymdownx.superfences
  - pymdownx.tasklist:
      custom_checkbox: true

extra:
  social:
    - icon: fontawesome/brands/github
      link: https://github.com/labilezhu/everlingo
```

构建：

```bash
mkdocs build
```

本地预览：

```bash
mkdocs serve
```

FastAPI 可以直接托管：

```text
http://localhost:8000/wiki/
```

---

# Wiki 首页建议

`memory/README.md` 可以这样设计：

```markdown
---
title: EverLingo Memory Wiki
---

# EverLingo Memory Wiki

欢迎来到你的外语学习记忆库。

## 快速入口

- [用户画像](./USER.md)
- [今日待复习](./review/due.md)
- [英语词汇](./items/en/vocab/)
- [日语词汇](./items/ja/vocab/)
- [语法笔记](./items/ja/grammar/)
- [错题集](./mistakes/)
- [阅读上下文](./contexts/)
- [学习事件](./events/)

## 最近学习

<!-- Agent 可以自动更新这里 -->

- 曖昧
- take for granted
- て形
- skip recalculating

## 薄弱点

<!-- 根据 mastery / lapses 自动生成 -->

- 日语：助词 `は` / `が`
- 英语：冠词 `a` / `the`
```

---

# 文件命名建议

建议使用：

```text
{slug}--{ulid}.md
```

例如：

```text
ambiguous--01JZABC456.md
aimai--01JZABD123.md
te-form--01JZABE001.md
```

原因：

- `slug` 方便人类浏览；
- `ulid` 保证稳定唯一；
- 文件名改变时也能通过 `id` 追踪；
- 避免同名词条冲突。

对于日语、中文、德语法语特殊字符，建议：

```text
headword: 曖昧
reading: あいまい
file: aimai--01JZABD123.md
```

浏览器 URL 会更干净。

---

# Markdown 链接规范

推荐优先使用标准 Markdown 相对链接：

```markdown
[曖昧](../../items/ja/vocab/aimai--01JZABD123.md)
```

不建议一开始重度依赖 Obsidian 专属语法：

```markdown
[[曖昧]]
```

原因是标准 Markdown 更适合：

- GitHub 浏览；
- MkDocs；
- 静态站点；
- 未来迁移。

如果你喜欢 WikiLink，可以通过 `mkdocs-roamlinks-plugin` 支持，但内部存储仍建议能兼容标准 Markdown。

---

# SQLite 索引设计

Markdown 文件是源数据，SQLite 是可重建索引。

建议放在：

```text
data/users/default/index/memory.sqlite
```

可以有几张表：

```sql
CREATE TABLE documents (
  id TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  type TEXT NOT NULL,
  lang TEXT,
  title TEXT,
  headword TEXT,
  updated_at TEXT,
  frontmatter_json TEXT,
  body TEXT
);

CREATE VIRTUAL TABLE documents_fts USING fts5(
  title,
  headword,
  body,
  tags,
  content='documents',
  content_rowid='rowid'
);

CREATE TABLE aliases (
  alias TEXT NOT NULL,
  document_id TEXT NOT NULL,
  lang TEXT,
  PRIMARY KEY(alias, document_id)
);

CREATE TABLE links (
  from_id TEXT NOT NULL,
  to_id TEXT NOT NULL,
  link_type TEXT
);
```

如果要做向量检索，可以加：

```text
embeddings.sqlite
```

或者用：

- `sqlite-vec`
- Chroma
- FAISS
- LanceDB

我个人更推荐早期用：

```text
SQLite FTS5 + sqlite-vec
```

因为部署简单，文件少，符合你的轻量开源项目定位。

---

# 复习系统建议

## 初期

直接把复习状态存在 Markdown Frontmatter：

```yaml
mastery: 0.42
due_at: 2026-06-28T09:00:00+08:00
ease: 2.3
interval_days: 2
lapses: 1
```

优点：

- 简单；
- 可读；
- Wiki 里直接看到；
- Git 可追踪。

缺点：

- 高频复习会频繁改文件。

---

## 中后期

把高频变化的调度状态迁移到 SQLite，但 Markdown 仍保留摘要。

推荐：

```text
review/cards/*.md        # 卡片定义，人类可读
index/review.sqlite      # 调度状态，高频更新
```

也就是说：

- 卡片内容在 Markdown；
- 复习算法状态在 SQLite；
- Wiki 展示时合并渲染。

这样更适合以后做主动推送。

---

# 记忆更新流程

一次用户查询可以这样处理：

```text
用户：曖昧 是什么意思？
  ↓
Agent 回答用户
  ↓
Memory Extractor 判断是否需要记忆
  ↓
生成 Memory Ops
  ↓
Memory Writer upsert Markdown
  ↓
更新 SQLite FTS / Vector Index
  ↓
更新 review due
  ↓
Wiki 自动可浏览
```

可以分成两个 Agent / Chain：

```text
Chat Agent
  负责回答问题

Memory Agent
  负责提取、合并、更新记忆
```

这样 Chat Agent 不会被记忆写入逻辑污染。

---

# Memory Ops 类型建议

建议先支持这些操作：

```text
upsert_user_profile
upsert_vocab
upsert_phrase
upsert_grammar
upsert_mistake
append_event
append_context
increment_seen_count
link_context_to_item
create_review_card
update_review_state
merge_items
add_alias
```

示例：

```json
{
  "ops": [
    {
      "type": "upsert_vocab",
      "lang": "ja",
      "headword": "曖昧",
      "reading": "あいまい",
      "summary": "不明确、含糊、模棱两可。",
      "tags": ["ja", "vocab", "confusing"]
    },
    {
      "type": "append_context",
      "source_type": "chat",
      "lang": "ja",
      "content": "用户询问「曖昧」是什么意思，并想知道和中文「暧昧」的区别。"
    },
    {
      "type": "create_review_card",
      "target_headword": "曖昧",
      "card_type": "meaning"
    }
  ]
}
```

---

# Agent Prompt 注入建议

System Prompt 可以组织成：

```text
你是 EverLingo，一个有记忆的 AI 外语老师。

以下是用户画像：
<USER_PROFILE>
...

以下是与当前问题相关的长期记忆：
<RELEVANT_MEMORY>
...

以下是今天到期的复习项目：
<DUE_REVIEWS>
...

回答要求：
1. 根据用户水平解释。
2. 如果用户重复查询，提醒但不要责备。
3. 如果发现新词、新短语、新错误，生成 memory_ops。
4. 不要编造用户记忆。
```

关键点：

> **用户画像全量注入，长期知识检索注入，事件记忆摘要注入。**

---

# 为什么不要只用向量数据库？

不建议一开始把长期记忆直接放进向量数据库。

原因：

1. 用户无法浏览；
2. 无法手动编辑；
3. 不适合 Git；
4. 复习调度不透明；
5. 很难做高质量 Wiki；
6. 容易变成黑盒记忆。

更适合你的产品的是：

> **Markdown 负责“记得清楚”，向量索引负责“找得快速”。**

---

# 为什么不要用 Notion / Logseq / Obsidian 作为核心依赖？

这些工具都很好，但不适合作为你的底层产品依赖。

| 工具 | 问题 |
|---|---|
| Notion | 闭源、API 限制、用户数据不可控 |
| Obsidian | 很适合个人使用，但不适合作为服务端核心依赖 |
| Logseq | Outliner 模型较强，但对普通用户 Wiki 浏览不如 Markdown 静态站直观 |
| 纯数据库 | Agent 友好，但人类不可直接编辑 |
| 纯向量库 | 召回可以，知识管理不行 |

你可以做到：

> **兼容 Obsidian 风格，但不依赖 Obsidian。**

---

# 推荐开发阶段

## 第一阶段：文件记忆跑通

目标：让 Agent 可以稳定写 Markdown。

实现：

- `USER.md`
- `events/`
- `items/{lang}/vocab/`
- `items/{lang}/phrases/`
- `items/{lang}/grammar/`
- `mistakes/`
- 基础 `MemoryWriter`
- 基础 `MemoryRetriever`

暂时可以不做向量索引，只用文件扫描和关键词匹配。

---

## 第二阶段：Wiki 浏览

目标：让用户能浏览自己的学习资产。

实现：

- 接入 MkDocs Material；
- FastAPI 托管 `/wiki/`；
- 首页自动生成；
- 标签和目录自动生成；
- 每次记忆更新后异步重建 Wiki。

---

## 第三阶段：搜索和召回

目标：Agent 真正“越用越懂你”。

实现：

- Markdown parser；
- SQLite FTS5；
- alias 检索；
- language filter；
- Top K relevant memory 注入；
- 重复查询检测。

---

## 第四阶段：复习系统

目标：从“记录”变成“教学”。

实现：

- `review/cards/`；
- `due_at`；
- 掌握度；
- 微信主动推送；
- 每日复习；
- 错题强化练习。

---

## 第五阶段：浏览器插件

目标：查询即记录。

实现：

- 划词；
- 捕获网页 URL、标题、段落；
- 存入 `contexts/web/`；
- 自动链接到词汇 / 短语；
- 生成阅读 Wiki。

---

# 最小可用实现建议

你可以先实现这个最小结构：

```text
memory/
  README.md
  USER.md
  events/
    2026-06-26.md
  items/
    ja/
      vocab/
      phrases/
      grammar/
    en/
      vocab/
      phrases/
      grammar/
  review/
    due.md
```

然后加一个 Python 类：

```text
MemoryStore
MemoryRetriever
MemoryWriter
MemoryIndexer
```

职责：

```text
MemoryStore
  管理 vault 路径、文件读写、frontmatter 解析

MemoryRetriever
  根据用户输入检索相关 Markdown

MemoryWriter
  根据 Memory Ops 更新 Markdown

MemoryIndexer
  重建 SQLite FTS / Vector Index
```

---

# 最终推荐结论

对「记了么」来说，最合适的 Agent 记忆结构是：

```text
Markdown Vault
+ YAML Frontmatter
+ Wiki 目录结构
+ MkDocs Material 浏览
+ SQLite FTS5 检索
+ 可选 Vector Index
+ Structured Memory Ops 写入
```

这套方案有几个关键优势：

1. **用户真的能看到 AI 记住了什么**；
2. **学习记录天然变成 Wiki**；
3. **Agent 可以稳定读写**；
4. **开源项目部署简单**；
5. **适合微信、Web、TUI、多端共用**；
6. **方便以后做浏览器插件和主动复习**；
7. **不会被数据库或 SaaS 工具锁死**。

最重要的是，它和你的产品理念非常一致：

> **查过，不等于记下。  
> Markdown Wiki 让每一次查询都沉淀成可浏览、可复习、可修改的学习资产。**