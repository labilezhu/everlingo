### vocab 文件 vocab/

文件名与路径，例如：
```text
vocab/aimai--01JZABD123.md
```

#### Markdown Frontmatter 字段补充说明

```yaml
ulid: 01JZABD123
type: vocab
headword: 曖昧
slug: aimai
title: '"曖昧" 释义'
description: '"曖昧" 释义'
description_in_target_lang: 「曖昧」の定義
created_at: 2026-06-22T18:08:00+08:00
timestamp: 2026-06-26T09:15:00+08:00
first_seen: 2026-06-22T18:08:00+08:00
last_seen: 2026-06-26T09:15:00+08:00
seen_count: 4
aliases:
  - あいまい
  - ambiguous
tags: []
related:
  - 明確
  - はっきり
  - 微妙
schema_version: 1
```

字段说明:
headword: 词汇本身

slug: 
源于 `headword`，如非英文，需要转换：
- 中文的：headword="男人" ，用英文词同义词 "man" 
- 日语，headword="曖昧" 则用发音词 "aimai"
最后注意按照 “slug 基础规则” 说明处理

#### markdown 主体内容

```markdown
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

