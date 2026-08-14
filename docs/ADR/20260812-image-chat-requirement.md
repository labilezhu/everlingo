# EverLingo 聊天图片学习能力产品需求文档

## 1. 背景与目标

EverLingo 当前的核心交互是用户通过聊天与 AI 进行语言学习。现实中的学习内容并不总是以文本形式存在，用户经常通过照片、截图、教材、试卷、网页、视频字幕、商品包装等方式接触语言内容。

因此，需要在聊天中增加图片输入能力，使用户能够直接将图片作为当前对话的上下文，由 AI 对图片内容进行识别、理解、解释和进一步处理。

本需求的目标不是建设一个独立 OCR 功能，而是建立：

> **图片作为学习 Context → AI 理解用户意图 → 执行学习任务 → 可选地沉淀为 Note / Memory**

整个能力应与现有聊天、Agent、Note、Memory、Recall 等能力保持一致。

---

# 2. 产品目标

## 2.1 核心目标

用户能够：

1. 在聊天中直接上传或拍摄图片。
2. AI 自动理解图片中的语言学习内容。
3. 根据用户问题执行不同任务，例如：

   * 解释
   * 翻译
   * 做题
   * 分析错误
   * 提取重点
   * 整理内容
   * 提取学习知识点
4. 用户可以继续围绕同一图片进行多轮对话。
5. 用户可以将图片中的重要学习内容沉淀为 EverLingo Note / Memory。

## 2.2 非目标

本阶段不把以下能力作为独立产品目标：

* 专业级通用 OCR
* 通用图像搜索
* 图片编辑
* 图片生成
* 专业文档扫描
* 通用视觉问答平台

这些能力只有在服务语言学习场景时才需要重点支持。

---

# 3. 核心产品模型

图片在 EverLingo 中不是一种最终内容，而是一种 **学习上下文输入（Learning Context Input）**。

系统处理链路：

```text
用户上传图片
    ↓
图片预处理
    ↓
Vision Model 分析
    ↓
识别图片中的学习内容
    ↓
识别用户当前 Intent
    ↓
执行学习任务
    ↓
生成回答
    ↓
用户继续对话
    ↓
可选：生成 Note / Memory
```

可以进一步抽象成：

```text
Image
  ↓
Context Understanding
  ↓
Intent Understanding
  ↓
Task Execution
  ↓
Learning Result
  ↓
Memory Candidate
```

其中：

* Image：用户上传的图片
* Context：图片中包含的文本、题目、文章、知识点等
* Intent：用户希望对图片做什么
* Task：系统实际执行的学习任务
* Learning Result：用户得到的解释、答案或知识
* Memory Candidate：可能值得保存的长期学习内容

---

# 4. 用户场景模型

图片能力不按照图片类型设计，而按照用户任务设计。

核心任务分为五类：

| Task       | 用户目的   | 示例          |
| ---------- | ------ | ----------- |
| Understand | 看懂内容   | “这句话什么意思？”  |
| Solve      | 解决问题   | “这道题怎么做？”   |
| Explore    | 深入理解   | “这里为什么这样写？” |
| Organize   | 整理内容   | “帮我整理这页笔记。” |
| Remember   | 保存学习内容 | “这个帮我记一下。”  |

图片类型只是 Context Source。

例如：

```text
英语题
  → Solve

教材句子
  → Understand

文章截图
  → Explore

手写笔记
  → Organize

优秀表达
  → Remember
```

同一张图片可以对应不同 Intent。

例如同一张英语题：

```text
“这是什么意思？”
    → Understand

“帮我做一下。”
    → Solve

“为什么选 B？”
    → Explore

“把这个语法点记下来。”
    → Remember
```

因此系统不能根据图片类型单独决定执行任务。

---

# 5. 核心用户场景

## 5.1 场景 A：解释图片中的英文

### 输入

用户上传图片：

```text
I'm afraid that's not quite the case.
```

用户：

> 这句话什么意思？

### 系统行为

系统识别：

```text
Image Content:
English sentence

User Intent:
Understand

Task:
Explain sentence
```

输出：

* 当前语境下的含义
* 重点单词
* 语法结构
* 必要时提供例句

系统不应只返回 OCR 文本。

### 验收标准

用户不需要先手动 OCR，再把文本复制到聊天框。

---

## 5.2 场景 B：英语题目

### 输入

用户上传：

```text
I have lived here _____ 2019.

A. for
B. since
C. during
D. from
```

用户：

> 帮我做一下。

### 系统行为

识别：

```text
Content Type:
English Exercise

Intent:
Solve

Task:
Question Solving
```

输出：

```text
Answer:
B

Reason:
2019 是具体时间点，因此使用 since。
```

允许继续追问：

> for 和 since 的区别是什么？

系统继续使用当前图片上下文，而不是要求用户重新上传。

---

## 5.3 场景 C：解释错误原因

### 输入

用户上传已经完成的错题。

用户：

> 我为什么错了？

系统需要识别：

```text
Question
User Answer
Correct Answer
Knowledge Point
Error Pattern
```

输出：

```text
正确答案：B

你的错误：
把表示“时间点”的 2019 当成了时间段来处理。

相关知识点：
since + point in time
for + duration
```

这是比“给出正确答案”更高价值的学习场景。

---

## 5.4 场景 D：发现值得学习的内容

### 输入

用户上传一页英文文章。

用户：

> 这页有什么值得学的？

系统进行：

```text
Image
  ↓
Extract language content
  ↓
Identify vocabulary / expressions / grammar
  ↓
Evaluate learning value
  ↓
Select important items
```

输出例如：

```text
值得学习：

1. come across
   常用于“偶然遇到”

2. in the long run
   表示“从长期来看”

3. be reluctant to
   表示“不太愿意做某事”
```

系统可以进一步根据用户已有 Memory 判断：

* 是否已经学过
* 是否重复出现
* 是否值得复习

这是 EverLingo 图片能力的重点差异化场景。

---

## 5.5 场景 E：现实生活中的英文

例如：

```text
Keep refrigerated after opening.
```

用户拍摄食品包装。

用户：

> 这是什么意思？

系统回答：

> 开封后需冷藏。

进一步可以解释：

```text
refrigerated
这里表示“冷藏”，不是“冷冻”。
```

该场景的特点：

```text
非学习环境
    ↓
现实中遇到英文
    ↓
临时产生学习需求
    ↓
图片成为 Context
```

这是 EverLingo 的典型“Contextual Learning”场景。

---

## 5.6 场景 F：整理学习资料

用户上传：

* 手写笔记
* 课堂笔记
* 错题本
* 多张截图

用户：

> 帮我整理一下。

系统执行：

```text
Image Recognition
    ↓
Content Extraction
    ↓
Topic Classification
    ↓
Knowledge Point Extraction
    ↓
Structured Note
```

最终输出可以形成：

```text
Topic:
Present Perfect

Key Points:
- since / for
- have + past participle

Common Error:
since / for 混淆
```

用户可以进一步：

> 保存。

然后生成 Note。

---

# 6. 图片输入后的系统流程

## 6.1 总体流程

```text
             ┌──────────────┐
             │    用户聊天    │
             └──────┬───────┘
                    │
             上传图片 + 文本
                    │
                    ▼
           ┌─────────────────┐
           │ Image Preprocess │
           └────────┬────────┘
                    │
                    ▼
           ┌─────────────────┐
           │ Vision Analysis │
           └────────┬────────┘
                    │
                    ▼
           ┌─────────────────┐
           │ Context Analysis│
           └────────┬────────┘
                    │
                    ▼
           ┌─────────────────┐
           │ Intent Analysis │
           └────────┬────────┘
                    │
                    ▼
           ┌─────────────────┐
           │   Task Execute  │
           └────────┬────────┘
                    │
                    ▼
             ┌────────────┐
             │  Chat Reply │
             └─────┬──────┘
                   │
                   ▼
          ┌───────────────────┐
          │ Memory Candidate? │
          └─────────┬─────────┘
                    │
              Yes ──┴── No
               │        │
               ▼        ▼
            Note/Memory  End
```

---

# 7. 图片 Context 分析

Vision Model 返回的结果不应只包含 OCR Text。

建议形成内部标准化结构：

```json
{
  "content_type": "english_exercise",
  "language": "en",
  "text": "...",
  "elements": [
    {
      "type": "question",
      "content": "...",
      "options": [
        {"label": "A", "text": "..."},
        {"label": "B", "text": "..."}
      ]
    }
  ],
  "learning_points": [
    {
      "type": "grammar",
      "content": "since vs for"
    }
  ]
}
```

后续 Agent 使用这个 Context，而不是直接依赖原始 OCR。

---

# 8. Intent 识别

## 8.1 Intent 来源

Intent 优先从用户自然语言中获得。

例如：

```text
图片 + “这是什么意思？”
→ understand

图片 + “帮我做一下”
→ solve

图片 + “为什么选 B？”
→ explain

图片 + “有什么值得学？”
→ explore

图片 + “帮我记下来”
→ remember
```

## 8.2 没有文字时

用户可能只上传图片。

此时：

```text
Image
  ↓
Content Classification
  ↓
Generate Suggested Actions
```

例如检测到英语题：

```text
我看到了 5 道英语题。

你可以：
[逐题讲解]
[检查答案]
[提取知识点]
```

检测到英文文章：

```text
我看到一篇英文文章。

你可以：
[总结]
[解释重点表达]
[找值得学习的内容]
```

不建议系统在用户没有明确意图时直接执行复杂操作。

---

# 9. Chat 上下文管理

图片上传后，应进入当前 conversation context。

例如：

```text
User:
[Image]

User:
这句话什么意思？

Assistant:
...

User:
这里的 mind 为什么不是“介意”？

Assistant:
...
```

第二个问题不需要重新上传图片。

系统需要知道：

```text
Current Conversation
    +
Image Context
    +
Previous User Intent
    +
Previous Assistant Answer
```

从而保持上下文连续性。

---

# 10. Memory / Note 处理

图片本身不是默认 Memory。

例如用户上传：

```text
📷 一篇文章
```

不能自动把整张图片保存为 Memory。

系统应该区分：

```text
Raw Input
    ↓
Learning Content
    ↓
Learning Candidate
    ↓
User Confirmation
    ↓
Memory
```

只有当用户：

* 明确要求保存
* 或 Agent 根据产品策略建议保存并得到用户确认

才创建长期 Note / Memory。

---

# 11. 推荐的 Memory 数据结构

图片来源的 Note 应保存原始 Context。

例如：

```json
{
  "source": "image",
  "source_context": {
    "image_id": "...",
    "original_text": "..."
  },
  "learning_content": {
    "type": "expression",
    "content": "mind the gap",
    "meaning": "小心站台间隙"
  },
  "conversation_context": {
    "question": "为什么 mind 在这里不是介意？"
  }
}
```

这里 `source_context` 很重要。

以后 Recall 时可以告诉用户：

> 你之前是在机场看到 “Mind the gap” 时学到这个表达的。

这才能真正发挥 EverLingo 的 Context Memory 能力。

---

# 12. UI / UX 要求

## 12.1 输入框

聊天输入框增加：

```text
[ + ] [ 📷 ] [ 输入消息…… ] [发送]
```

支持：

* 拍照
* 相册选择
* 文件/图片选择
* 粘贴截图

具体能力按照 Web / Mobile 平台分别实现。

---

## 12.2 上传状态

图片上传后显示：

```text
┌───────────────────┐
│      image        │
│                   │
└───────────────────┘
```

允许在发送之前删除或更换图片。

---

## 12.3 AI 处理中

不要求用户看到 OCR、Vision Model 等内部技术状态。

可以表现为：

> 正在查看这张图片……

然后正常输出回答。

---

## 12.4 自动建议

仅在系统能够较高置信度识别图片类型时提供建议。

例如：

```text
我看到了一个英语选择题。

[帮我做]
[讲解语法]
[提取知识点]
```

建议项本质上是快捷 Intent，不应该形成新的复杂导航。

---

# 13. 图片类型分类

内部可以定义 Content Type：

```text
TEXT
SENTENCE
VOCABULARY
ARTICLE
EXERCISE
WRONG_ANSWER
NOTE
SCREENSHOT
MENU
PRODUCT_LABEL
SIGN
CHART
OTHER
```

但这些类型主要用于：

* Prompt 路由
* Agent Tool 路由
* UI Suggestion
* 数据分析
* Memory 分类

不建议暴露给用户要求用户主动选择。

---

# 14. Agent / Model 层设计

建议分成三个逻辑阶段，而不一定对应三个独立模型调用。

## Stage 1：Vision Understanding

负责：

```text
What is in the image?
```

输出：

```text
OCR
Layout
Language
Question
Vocabulary
Learning Content
```

---

## Stage 2：Intent Understanding

负责：

```text
What does the user want to do with this content?
```

输入：

```text
Image Context
+
User Message
+
Conversation History
```

输出：

```text
understand
solve
explore
organize
remember
```

---

## Stage 3：Task Execution

根据 Intent 执行：

```text
understand → explanation
solve      → reasoning / answer
explore    → deeper analysis
organize   → structured note
remember   → memory creation
```

这样可以避免把所有逻辑堆积到一个巨大 Prompt 中。

---

# 15. MVP 范围

第一版本建议只实现以下能力：

## P0

### 1. 图片上传

支持：

* JPG
* JPEG
* PNG
* WebP

### 2. 图片理解

支持：

* 英文 OCR
* 中英文混合文本
* 单词
* 句子
* 段落
* 英语题目

### 3. 基础 Intent

支持：

```text
Understand
Solve
Explain
Explore
Remember
```

### 4. 多轮图片对话

同一图片在 conversation 生命周期内保持可引用。

### 5. Memory

支持：

```text
“帮我记下来”
```

将当前学习内容转换为 Note / Memory。

---

# 16. P1

加入：

```text
Wrong Answer Analysis
Note Organization
Learning Point Extraction
Multiple Images
Image Comparison
Handwritten Notes
```

特别是：

> **多图片 → 整理成一个学习主题**

例如用户连续上传 5 张错题：

```text
5 张错题
   ↓
识别
   ↓
归类
   ↓
发现共同错误
   ↓
生成 Review Note
```

---

# 17. P2

进一步支持：

```text
图片自动生成学习卡片
图片自动生成复习题
图片 → Vocabulary Set
图片 → Grammar Review
图片 → Spaced Repetition
```

例如：

```text
一页文章
   ↓
提取 8 个重点表达
   ↓
用户选择 5 个
   ↓
生成 Vocabulary Memory
   ↓
未来 Recall
   ↓
Spaced Review
```

---

# 18. 产品成功标准

不能仅用“OCR 准确率”衡量。

建议指标分成四层。

## Input

```text
Image Upload Success Rate
Image Processing Success Rate
Vision Recognition Success Rate
```

## Understanding

```text
Intent Recognition Accuracy
Content Classification Accuracy
```

## Task

```text
Answer Quality
Explanation Quality
Question Solving Accuracy
```

## Learning

最重要：

```text
Memory Creation Rate
Memory Recall Rate
Image → Note Conversion Rate
Learning Session Continuation Rate
```

尤其需要关注：

> **用户上传图片后，是否继续进行第二轮、第三轮学习对话。**

如果用户上传图片后只得到一次 OCR 文本，然后结束，那么这个能力仍然只是 OCR。

如果：

```text
Image
 ↓
Question
 ↓
Explanation
 ↓
Follow-up
 ↓
Learning Point
 ↓
Memory
```

则说明图片已经真正融入 EverLingo 的学习闭环。

---

# 19. 产品原则

最后确定几个研发实现过程中需要保持稳定的原则。

### 原则 1：图片是 Context，不是最终结果

系统首先理解图片，然后根据用户意图处理。

### 原则 2：Intent 优先于 Image Type

同一图片可以触发完全不同的任务。

### 原则 3：聊天优先于菜单

优先让用户自然表达需求，不要求用户先选择功能。

### 原则 4：不默认保存图片为 Memory

Memory 保存的是学习价值，而不是原始输入。

### 原则 5：保留学习 Context

Memory 应知道：

```text
用户在哪里遇到
什么内容
问了什么
为什么学习
```

### 原则 6：图片能力最终服务于 Recall

图片上传本身不是终点。

最终目标是：

```text
Image
 ↓
Learning
 ↓
Memory
 ↓
Future Recall
```

---

# 20. 一句话定义

从研发和产品架构角度，可以将本能力定义为：

> **Chat Image Learning：允许用户将图片作为当前学习 Context，通过自然语言与 AI 进行理解、解题、分析、整理，并将有价值的学习内容沉淀到 EverLingo Memory。**

核心流程：

```text
Upload
  ↓
Understand Context
  ↓
Infer Intent
  ↓
Execute Learning Task
  ↓
Continue Conversation
  ↓
Capture Learning Point
  ↓
Save Memory
  ↓
Recall Later
```
