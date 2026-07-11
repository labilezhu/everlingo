### phrase 文件 phrase/

文件名与路径，例如：

```text
phrase/take-for-granted--01JZABC789.md
```


#### Markdown Frontmatter 字段补充说明

```yaml
ulid: 01JZABC789
type: phrase
headword: take for granted
slug: take-for-granted
title: '"take for granted" 词汇'
description: '"take for granted" 词汇'
description_in_target_lang: 'The phrase "take for granted"'
created_at: 2026-06-20T21:00:00+08:00
timestamp: 2026-06-26T08:30:00+08:00
aliases:
  - taken for granted
tags:
  - workplace
first_seen: 2026-06-20T21:00:00+08:00
last_seen: 2026-06-26T08:30:00+08:00
seen_count: 3
schema_version: 1
```

字段说明:
headword: phrase 本身

slug: 
源于 `headword`，如非英文，需要转换：
- 中文的：headword="男人" ，用英文词同义词 "man" 
- 日语，headword="曖昧" 则用发音词 "aimai"
最后注意按照 “slug 基础规则” 说明处理

#### markdown 主体内容

```markdown

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


