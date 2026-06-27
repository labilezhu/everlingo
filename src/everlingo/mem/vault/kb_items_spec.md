# 知识点类 memory items

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

