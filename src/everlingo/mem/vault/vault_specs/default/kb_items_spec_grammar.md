### grammar 文件 grammar/

文件名与路径，例如：
```text
grammar/te-form--01JZABE001.md
```

#### Markdown Frontmatter 字段补充说明

```yaml
ulid: 01JZABE001
type: grammar
title: TE形 语法
headword: TE形
slug: te-form
description: TE形 语法
description_in_target_lang: 「て」形の文法
created_at: 2026-06-24T10:00:00+08:00
timestamp: 2026-06-26T10:10:00+08:00
seen_count: 1
tags: []
first_seen: 2026-06-24T10:00:00+08:00
last_seen: 2026-06-26T10:10:00+08:00
schema_version: 1
```

字段说明:
headword: 使用`目标学习语言` 用最少的文字命名语法知识点
slug: 源于 `headword`。翻译成英文。最后注意按照 “slug 基础规则” 说明处理

#### markdown 主体内容

```markdown
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

