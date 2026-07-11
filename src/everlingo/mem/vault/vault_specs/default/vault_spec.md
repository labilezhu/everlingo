# 单语言 Memory Vault Spec

由 markdown 文件、结构化目录组成的 memory vault。 用于记录用户的语言学习事件，语言知识点。

单语言 vault 目录结构示例：
```bash
spec/ # Memory Vault 目录结构规范，知识点文件规范。目录一定存在。在浏览、读、写、搜索 vault 前，通过阅读其中的 spec 文件可以了解相关规范和术语。
  vault_spec.md # vault 整体结构与文件规范
  events_spec.md # events 目录下的事件文件规范
  kb_items_spec.md # items 目录下的知识点文件规范
events/
  2026/
    06/
      2026-06-26.md
items/ # 知识点类 memory items
  vocab/
    gcc--01JZABC123.md
    ambiguous--01JZABC456.md
  phrase/
    take-for-granted--01JZABC789.md
  grammar/
    present-perfect--01JZABD001.md
  pragmatics/ # 语用
  others/ # 其它分类
tmp/ # 程序内部使用的临时文件，没有用户数据价值。不索引此目录
```

## Markdown 文件使用什么语言编写
文件的主要是给语言学习者阅读的笔记。所以，默认情况下，主要语言应该是 `界面语言` 。但对`目标学习语言` 引用，如`目标学习语言` 的词语、例句、示例、术语等等，应该使用 `目标学习语言`。

## /events 事件

事件文件保存于 /events 目录下。

在读写 events/ 目录及子目录下的任何文件前，务必阅读以下规范，了解文件结构与意义：
[events_spec.md](events_spec.md)

## /items 知识点 

知识点目录由 markdown 文件、结构化目录组成。 用于记录用户的语言学习事件，语言知识点。记录真正沉淀下来的知识点。

知识点文件保存于 /items 目录下。

### 定义

- `知识点目录`： /items 目录
- `知识点`：指学习语言时的一个具体的知识，如 词汇、短语、语法、语用。

- `知识点条目` ：也叫 `知识点文件`。一个保存 `知识点` 的 markdown 文件。
  - 相同的 `知识点` 只能有一个 `知识点条目`。所有`知识点`的内容都必须合并到同一`知识点条目`

- `知识类型`，也叫 `知识点类型`，也叫 `type` 或 `item type`，包括以下分类: 
  - vocab
  - phrase
  - grammar
  - pragmatics
  - others

### 知识点目录结构

按不同`知识类型`划分子目录。示例
```
vocab/ # 词汇
  gcc--01JZABC123.md
  ambiguous--01JZABC456.md
phrase/ # 短语
  take-for-granted--01JZABC789.md
grammar/ # 语法
  present-perfect--01JZABD001.md
pragmatics/ # 语用  
others/ # 其它分类    
```

### 基础规则

#### slug 基础规则
用于将来生成 wiki 静态网站时作为人类友好的 url 部分。使用 url 安全的英文字符集(所以必要时需要翻译成英文)。但不能使用各操作系统或 url 要转义或不安全的文件名字符，如有，去掉之。空格变为"-"。

### Markdown Frontmatter 字段

以下所有 frontmatter 字段（**必选**）：

字段示例：
```yaml
ulid: 01JZABD123
slug: pragmatically-answering-yes-or-no-can-easily-lead-to-confusion
type: pragmatics
title: 语用学上，回答 Yes 或 No 时容易混淆
description: 语用学上，回答 Yes 或 No 时容易混淆
description_in_target_lang: 'Pragmatically, answering "Yes" or "No" can easily lead to confusion.'
created_at: 2026-06-22T18:08:00+08:00
timestamp: 2026-06-26T09:15:00+08:00
schema_version: 1
first_seen: 2026-06-22T18:08:00+08:00
last_seen: 2026-06-26T09:15:00+08:00
seen_count: 4
tags:
```

字段说明：
ulid: 同文件命名格式中的 `ulid`。保证稳定唯一。
title: 使用`界面语言`，限一句话，描述本文件的知识点。用于语义搜索和 full text search。 OKF `title` 标准槽位，单句摘要。
description: 使用`界面语言`，限最多两句话，描述本文件的知识点。用于语义搜索和 full text search。 OKF `description` 标准槽位，单句摘要。
description_in_target_lang: 使用`目标学习语言`，限一句话，描述本文件的知识点。vault 扩展键（OKF 无对应字段）。用于 full text search。
created_at: 创建时间，ISO 8601。
timestamp: update time，使用格式 ISO 8601。OKF `timestamp` 标准槽位。
schema_version: int。当前 frontmatter schema 版本。
slug: 见 “具体 知识类型 的规范” 一节中，每个 `知识类型`，都有自己的 slug 说明。
type: 知识类型(item type): 对应不同子目录
- vocab
- phrase
- grammar
- pragmatics
- others

### 文件命名

文件命名格式：

```text
{slug}--{ulid}.md
```

例如：

```text
ambiguous--01JZABC456.md
aimai--01JZABD123.md
te-form--01JZABE001.md
```

注意：

- `slug` 文件名主体部分，方便人类找到文件。
- `ulid` 保证稳定唯一。
  - 文件名改变时也能通过 `ulid` 追踪；
  - 避免同名词条冲突。


### 关联字段

```yaml
aliases:
  - あいまい
related:
  - 明確
  - はっきり
  - 微妙
```

### 知识点通用 markdown 文件章节

#### 遇到记录

遇到记录。记录每次需要记忆当前知识点的 conversation context 。这个章节放文件最后。**每次读写本知识点文件时，都必须增加一行访问记录**。

```markdown
## 遇到记录

- 2026-06-22 13:41:18 ：微信中询问“曖昧”和中文“暧昧”的区别。
- 2026-06-26 18:42:48 ：阅读日语文章时再次遇到。
```


### 具体 知识类型 的规范
每种 `知识类型` 对应的 `知识点文件` 规范除上面介绍的通用 `知识点文件` 规范 外，还有每种类型的特定规范。在读写某一类`知识类型`文件前，务必阅读相关的 `知识类型` 的`知识点文件` 规范，了解具体`知识类型`的文件结构与意义：

- [vocab](kb_items_spec_vocab.md)
- [phrase](kb_items_spec_phrase.md)
- [grammar](kb_items_spec_grammar.md)
- [pragmatics](kb_items_spec_pragmatics.md)
- [others](kb_items_spec_others.md)
