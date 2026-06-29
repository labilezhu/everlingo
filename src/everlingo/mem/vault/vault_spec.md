# Memory Vault Runtime Spec

由 markdown 文件、结构化目录组成的 memory vault。 用于记录用户的语言学习事件，语言知识点。

Memory Vault 位于 $workspace/memory/ 目录下。

目录结构示例：
```bash
en/ # 目标学习语言
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
    pragmatics/ # 语用
    others/ # 其它分类

ja/
  events/
    2026/
      06/
        2026-06-26.md
  items/ #学习类 memory items
    vocab/
      曖昧--01JZABD123.md
    ...

tmp/ #程序内容使用的临时文件，没有用户数据价值。
```

以下 `$lang` 表示 en/ja 等等`目标学习语言`的编码。


## Markdown Frontmatter 通用字段字段

先定义一个轻量 schema，避免后面文件越来越乱。

### 通用字段

```yaml
title: 曖昧
created_at: 2026-06-26T10:00:00+08:00
updated_at: 2026-06-26T10:30:00+08:00
schema_version: 1
```

字段说明：
title: 知识点作为 wiki 文章时的标题。限最多一句话，描述本文件的内容。

## Markdown 文件使用什么语言编写
文件的主要是给语言学习者阅读的笔记。所以，默认情况下，主要语言应该是 `界面语言` 。但对`目标学习语言` 引用，如`目标学习语言` 的词语、例句、示例、术语等等，应该使用 `目标学习语言`。


## items/ 知识点类 memory items
{{ include [参考 kb_items_spec.md](./kb_items_spec.md) }}

## events/ 事件类
{{ include [参考 events_spec.md](./events_spec.md) }}

