# 知识点类 memory items


由 markdown 文件、结构化目录组成的 vault。 用于记录用户的语言学习事件，语言知识点。

记录真正沉淀下来的知识点。

目录结构示例：
```
    vocab/
      gcc--01JZABC123.md
      ambiguous--01JZABC456.md
    phrases/
      take-for-granted--01JZABC789.md
    grammar/
      present-perfect--01JZABD001.md
    pragmatics/ # 语用      
```


## 增加 Markdown Frontmatter 字段

```yaml
first_seen: 2026-06-22T18:08:00+08:00
last_seen: 2026-06-26T09:15:00+08:00
seen_count: 4
```

### 关联字段

```yaml
aliases:
  - あいまい
  - ambiguous
related:
  - 明確
  - はっきり
  - 微妙
```

## 知识点通用 markdown 文件章节

### 遇到记录 - encounter log

遇到记录，记录每次需要记忆当前知识点的 conversation context

```markdown
## 遇到记录

- 2026-06-22：微信中询问“曖昧”和中文“暧昧”的区别。
- 2026-06-26：阅读日语文章时再次遇到。
```

## 知识类型说明

知识类型 item types: 对应不同子目录
- vocab
- phrases
- grammar
- pragmatics

### vocab 文件 items/$lang/vocab/

例如：

```text
items/ja/vocab/曖昧--01JZABD123.md
```

内容：

```markdown
---
id: 01JZABD123
type: vocab
lang: ja
headword: 曖昧
aliases:
  - あいまい
  - ambiguous
tags:
  - ja
  - vocab
  - adjective
  - confusing
status: learning
first_seen: 2026-06-22T18:08:00+08:00
last_seen: 2026-06-26T09:15:00+08:00
seen_count: 4
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

```



### phrases 文件 items/$lang/phrases/



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
first_seen: 2026-06-20T21:00:00+08:00
last_seen: 2026-06-26T08:30:00+08:00
seen_count: 3
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



### grammar 文件 items/$lang/grammar/

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
first_seen: 2026-06-24T10:00:00+08:00
last_seen: 2026-06-26T10:10:00+08:00
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




