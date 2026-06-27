# Memory Vault

由 markdown 文件、结构化目录组成的 memory vault 。 保存于 [workspace](/docs/impl-spec/worksplace/workspace.md) 下的 memory 目录。



## 文件命名

文件命名格式：

```text
{file_name}--{ulid}.md
```

例如：

```text
ambiguous--01JZABC456.md
曖昧--01JZABD123.md
te-form--01JZABE001.md
```

原因：

- `main_file_name` 文件名主体部分，方便人类找到文件。一般同 “Markdown Frontmatter 字段规范” 的 “通用字段” 中的 `title`。但不能使用各操作系统或url要转义或不安全的文件名字符，如有，去掉之。空格变为下划线
- `ulid` 保证稳定唯一；
- 文件名改变时也能通过 `id` 追踪；
- 避免同名词条冲突。

对于日语、中文、德语法语特殊字符，建议：

```text
headword: 曖昧
reading: あいまい
file: 曖昧--01JZABD123.md
```

## Markdown Frontmatter 字段规范

先定义一个轻量 schema，避免后面文件越来越乱。

### 通用字段

```yaml
id: 01JZABD123
type: vocab
lang: ja
title: 曖昧
main_file_name: 曖昧
slug: aimei
tags:
  - vocab
status: learning
created_at: 2026-06-26T10:00:00+08:00
updated_at: 2026-06-26T10:30:00+08:00
schema_version: 1
```

描述：
id: 同文件命名格式中的 `ulid`
slug: 用于将来生成 wiki 静态网站时作为人类友好的 url 部分。源于 `title` 。使用来 url 安全的英文字符集。如
- 中文的："男人" ，用英文词同义词 "man" 
- 日语，"曖昧" 则用发音词 "aimai"


### 学习类字段

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


## 知识点类 memory items

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

## 遇到记录

- 2026-06-22：微信中询问“曖昧”和中文“暧昧”的区别。
- 2026-06-26：阅读日语文章时再次遇到。
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





# Agent 记忆分层设计

建议不要把所有记忆都叫 memory，而是分层。

## 1. Profile Memory

稳定用户画像。 具体见 [USER-spec.md](/docs/impl-spec/worksplace/USER-spec.md)

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



