# Memory Vault Runtime Spec

由 markdown 文件、结构化目录组成的 memory vault。 用于记录用户的语言学习事件，语言知识点。

目录结构示例：
```bash
en/
  events/
    2026/
      06/
        2026-06-26.md
  items/ # 知识点类 memory items
    vocab/
      gcc--01JZABC123.md
      ambiguous--01JZABC456.md
    phrases/
      take-for-granted--01JZABC789.md
    grammar/
      present-perfect--01JZABD001.md

ja/
  events/
    2026/
      06/
        2026-06-26.md
  items/ #学习类 memory items
    vocab/
      曖昧--01JZABD123.md
    phrases/
    grammar/
```

以下 `$lang` 表示 en/ja 等等`目标学习语言`的编码。

## 文件命名

文件命名格式：

```text
{main_file_name}--{ulid}.md
```

例如：

```text
ambiguous--01JZABC456.md
曖昧--01JZABD123.md
te-form--01JZABE001.md
2026-06-26--01JZABE001.md
```

注意：

- `main_file_name` 文件名主体部分，方便人类找到文件。一般同 “Markdown Frontmatter 字段规范” 的 “通用字段” 中的 `title`。但不能使用各操作系统或url要转义或不安全的文件名字符，如有，去掉之。空格变为下划线
- `ulid` 保证稳定唯一；
- 文件名改变时也能通过 `ulid` 追踪；
- 避免同名词条冲突。

## Markdown Frontmatter 字段

先定义一个轻量 schema，避免后面文件越来越乱。

### 通用字段

```yaml
id: 01JZABD123
type: vocab
title: 曖昧
main_file_name: 曖昧
slug: aimei
tags:
  - vocab
created_at: 2026-06-26T10:00:00+08:00
updated_at: 2026-06-26T10:30:00+08:00
schema_version: 1
```

描述：
id: 同文件命名格式中的 `ulid`
slug: 用于将来生成 wiki 静态网站时作为人类友好的 url 部分。源于 `title` 。使用来 url 安全的英文字符集。如
- 中文的："男人" ，用英文词同义词 "man" 
- 日语，"曖昧" 则用发音词 "aimai"

## items/ 知识点类 memory items
{{ include [参考 kb_items_spec.md](./kb_items_spec.md) }}

## events/ 事件类
{{ include [参考 events_spec.md](./events_spec.md) }}

