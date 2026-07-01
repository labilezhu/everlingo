# 知识点类 memory items


由 markdown 文件、结构化目录组成的 vault。 用于记录用户的语言学习事件，语言知识点。

记录真正沉淀下来的知识点。

目录结构示例：
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

## 基础规则

### slug 基础规则
用于将来生成 wiki 静态网站时作为人类友好的 url 部分。使用 url 安全的英文字符集(所以必要时需要翻译成英文)。但不能使用各操作系统或 url 要转义或不安全的文件名字符，如有，去掉之。空格变为"-"。

## 增加 Markdown Frontmatter 字段

在 [vault_spec.md](/src/everlingo/mem/vault/vault_spec.md) 的 “Markdown Frontmatter 通用字段” 基础上，增加几个**必选字段**

字段示例：
```yaml
ulid: 01JZABD123
slug: pragmatically-answering-yes-or-no-can-easily-lead-to-confusion
tags:
type: pragmatics
first_seen: 2026-06-22T18:08:00+08:00
last_seen: 2026-06-26T09:15:00+08:00
seen_count: 4
title: 语用学上，回答 Yes 或 No 时容易混淆
intro_in_interface_lang: 语用学上，回答 Yes 或 No 时容易混淆
intro_in_target_lang: 'Pragmatically, answering "Yes" or "No" can easily lead to confusion.'
```

字段说明：
ulid: 同文件命名格式中的 `ulid`。保证稳定唯一；
title: 使用`界面语言`，限一句话，描述本文件的知识点。用于语义搜索和 full text search。
intro_in_interface_lang: 同 title
intro_in_target_lang: 使用`目标学习语言`，限一句话，描述本文件的知识点。用于 full text search 。
slug: 下文中每类知识点，都有自己的 slug 提取说明

## 文件命名

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

- `slug` 文件名主体部分，方便人类找到文件。同 “Markdown Frontmatter 字段” 的 `slug`。
- `ulid` 保证稳定唯一；。同 “Markdown Frontmatter 字段” 的 `ulid`。
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

## 知识点通用 markdown 文件章节

### 遇到记录 - encounter log

遇到记录，记录每次需要记忆当前知识点的 conversation context 。这个章节放文件最后。

```markdown
## 遇到记录

- 2026-06-22：微信中询问“曖昧”和中文“暧昧”的区别。
- 2026-06-26：阅读日语文章时再次遇到。
```

## 知识类型说明

知识类型 item types: 对应不同子目录
- vocab
- phrase
- grammar
- pragmatics
- others

### vocab 文件 vocab/

文件名与路径，例如：
```text
ja/vocab/aimai--01JZABD123.md
```

#### Markdown Frontmatter 字段补充说明

```yaml
ulid: 01JZABD123
type: vocab
headword: 曖昧
slug: aimai
title: '"曖昧" 释义'
intro_in_interface_lang: '"曖昧" 释义'
intro_in_target_lang: 「曖昧」の定義
aliases:
  - あいまい
  - ambiguous
tags:
  - adjective
  - confusing
first_seen: 2026-06-22T18:08:00+08:00
last_seen: 2026-06-26T09:15:00+08:00
seen_count: 4
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


### phrase 文件 phrase/

文件名与路径，例如：

```text
en/phrase/take-for-granted--01JZABC789.md
```


#### Markdown Frontmatter 字段补充说明

```yaml
ulid: 01JZABC789
type: phrase
headword: take for granted
slug: take-for-granted
intro_in_interface_lang: '"take for granted" 词汇'
intro_in_target_lang: 'The phrase "take for granted"'
title: '"take for granted" 词汇'
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



### grammar 文件 grammar/

文件名与路径，例如：
```text
ja/grammar/te-form--01JZABE001.md
```

#### Markdown Frontmatter 字段补充说明

```yaml
ulid: 01JZABE001
type: grammar
title: TE形 语法
headword: TE形
slug: te-form
intro_in_interface_lang: TE形 语法
intro_in_target_lang: 「て」形の文法
seen_count: 1
tags:
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


### pragmatics 文件 pragmatics/

文件名与路径，例如：
```text
ja/pragmatics/pragmatically-answering-yes-or-no-can-easily-lead-to-confusion--01JZABE001.md
```

#### Markdown Frontmatter 字段补充说明

```yaml
ulid: 01JZABE001
slug: pragmatically-answering-yes-or-no-can-easily-lead-to-confusion
tags:
type: pragmatics
first_seen: 2026-06-22T18:08:00+08:00
last_seen: 2026-06-26T09:15:00+08:00
seen_count: 4
title: 语用学上，回答 Yes 或 No 时容易混淆
intro_in_interface_lang: 语用学上，回答 Yes 或 No 时容易混淆
intro_in_target_lang: 'Pragmatically, answering "Yes" or "No" can easily lead to confusion.'
```

字段说明：
slug: 
    源于 `intro_in_interface_lang`。最后注意按照 “slug 基础规则” 说明处理

#### markdown 主体内容


```markdown
# Yes、 No 的回答

别人问：

Didn't you go yesterday?

如果你去了，应该回答：

Yes, I did.

很多中国人会错误回答：

No.

因为他们是在回答"没有（不是没去）"，而英语回答的是事实。

这是典型的 pragmatics 问题

```

### others 文件 others/

文件名与路径，例如：
```text
ja/others/pragmatically-answering-yes-or-no-can-easily-lead-to-confusion--01JZABE001.md
```

#### Markdown Frontmatter 字段补充说明

```yaml
ulid: 01JZABD123
slug: take-off
tags:
type: others
first_seen: 2026-06-22T18:08:00+08:00
last_seen: 2026-06-26T09:15:00+08:00
seen_count: 4
title: 表示「离开」 Take off
intro_in_interface_lang: 表示「离开」 Take off
intro_in_target_lang: To express "leaving" - Take off
schema_version: 1
```

字段说明：
slug: 
    源于 `intro_in_interface_lang`。最后注意按照 “slug 基础规则” 说明处理

#### markdown 主体内容


```markdown
# Yes、 No 的回答

别人问：

Didn't you go yesterday?

如果你去了，应该回答：

Yes, I did.

很多中国人会错误回答：

No.

因为他们是在回答"没有（不是没去）"，而英语回答的是事实。

这是典型的 pragmatics 问题

```