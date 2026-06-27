

# Memory Vault


```bash
memory/
  USER.md
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

  mistakes/
    ja/
      particle-wa-ga--01JZABF001.md
    en/
      article-a-the--01JZABF002.md

  relations/
    tags.md

index/
  memory.sqlite
  embeddings.sqlite
```

## 词汇记忆文件 items/$lang/vocab/

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



## 短语文件 items/$lang/phrases/



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



## 语法点文件 items/$lang/grammar/

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



## 上下文文件 contexts

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



## 错题 / 误用文件 mistakes

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



# Markdown Frontmatter 字段规范

先定义一个轻量 schema，避免后面文件越来越乱。

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



# Agent 记忆分层设计

建议不要把所有记忆都叫 memory，而是分层。

## 1. Profile Memory

稳定用户画像。

位置：

```text
USER.md
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

## 5. Procedural Memory(暂不实现)

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

这样会稳定很多。

---

