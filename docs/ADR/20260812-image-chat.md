# EverLingo 图片学习能力后端 High-Level Design

相关文档：

- docs/impl-spec/chat-agent-spec.md
- src/everlingo/agents/spec/envelope_spec.md
- docs/ADR/20260812-image-chat-requirement.md



## 1. 文档目的

本文定义 EverLingo 在现有：

```text
Frontend:
  Vite
  React
  TailwindCSS
  shadcn/ui
  react-markdown

Backend:
  Python
  LangChain Agent
  OpenRouter LLM
```

架构基础上，新增“聊天图片输入与图片学习能力”的后端 High-Level Design。

重点解决：

1. 图片如何从前端传入后端。
2. 图片如何进入 LangChain Agent。
3. Vision Model 与 Agent 的职责边界。
4. 图片内容如何标准化。
5. Conversation / Message / Image / Learning Content / Memory 之间如何关联。
6. 前后端接口及交换数据结构如何定义。
7. 后续支持多种 Vision Model、异步处理、多图片和 Memory 的可扩展性。

本文不定义具体 React UI，也不绑定具体 OCR/Vision 模型实现。

---

# 2. Design Goals

## 2.1 Goals

系统应支持：

```text
User
  ↓
Chat Message + Image
  ↓
Backend
  ↓
Vision Analysis
  ↓
Structured Image Context
  ↓
LangChain Agent
  ↓
Learning Task
  ↓
Chat Response
  ↓
Optional Learning Memory
```

同时支持：

* 单图片
* 多图片
* 图片 + 文本
* 图片 + 多轮追问
* 图片学习结果转 Note / Memory
* Vision Model 可替换
* OpenRouter Provider / Model 可配置
* 流式输出
* 后续扩展 PDF / 文件 / 音频等其他 Context 类型

---

# 3. 核心架构原则

## 3.1 Image 不直接进入业务 Agent

推荐：

```text
Image
  ↓
Vision Service
  ↓
Image Context
  ↓
Agent
```

而不是：

```text
Image
  ↓
Agent
  ↓
Agent 内部自行 OCR / Vision
```

原因：

1. Vision 是独立能力。
2. Image Context 可以缓存。
3. 可以更换 Vision Model。
4. 可以做独立测试。
5. Agent 不需要处理图片编码、压缩、格式转换。
6. 后续可以支持预处理、OCR、Vision Router。

---

## 3.2 原始图片和“图片理解结果”分离

不要把：

```text
image bytes
```

直接作为 conversation message 的永久内容。

建议分为：

```text
ImageAsset
    +
ImageAnalysis
    +
ChatMessage
```

关系：

```text
ImageAsset
    │
    └── ImageAnalysis

ChatMessage
    │
    └── references ImageAsset
```

这样可以实现：

* 图片复用
* 分析结果缓存
* 删除原图但保留分析结果
* Model re-analysis
* 多轮会话复用

---

# 4. Logical Components

建议新增以下后端组件：

```text
                                                             
                                     ┌─────────────────────┐ 
                                     │ React Web / WeChat  │ 
                                     └──────────┬──────────┘ 
                                                │            
                                Channels:  Web / WeChat      
                                                │            
                                     ┌──────────▼──────────┐ 
          ┬──────────────────────────┼      Session        │ 
          │                          └──────────┬──────────┘ 
          │                                     │            
          │                          ┌──────────▼──────────┐ 
          │          ┌───────────────┤      Chat Agent     │ 
          │          │               └──────────┬──────────┘ 
          │          │                          │            
          │          │                          │            
          │          │                          │            
 ┌────────▼────────┐ │                          │            
 │  Image Service  │ │                          │            
 └─────────────────┘ │                          │            
                     │                          │            
                     ▼                          │            
            ┌────────────────┐         ┌────────▼────────┐   
            │ Vision Service │         │ LangChain Agent │   
            └───────┬────────┘         └────────┬────────┘   
                    │                           │            
                    ▼                           ▼            
            ┌────────────────┐         ┌─────────────────┐   
            │ Vision Model   │         │ OpenRouter LLM  │   
            │ MiMo-V2.5 etc. │         └─────────────────┘   
            └────────────────┘                               
                                                             
```

以下只说说新模块：

### Image Service

负责：

* upload
* image validation
* image metadata
* storage
* lifecycle

### Vision Service

负责：

* image preprocessing
* vision model invocation
* structured image analysis
* analysis caching

---

# 5. 数据模型总览

核心实体：

```text
Session
    │
    ├── UserMessage.envelope.chat
    │      │
    │      └── MessageAttachment
    │              │（关联）
    │              └──> ImageAsset
    │                      ^（关联）
    │                      └── ImageAnalysis
    │
    └── LearningEvent
               │
               └── Memory Candidate
```

建议至少定义以下数据结构：

```text
Conversation
Message
MessageAttachment
ImageAsset
ImageAnalysis
ImageContext
LearningTask
MemoryCandidate
```

---

# 6. UserMessage.envelope 数据结构

建议前后端统一使用：

```json
{
    "schema_version": 1,
    "role": "user",
    "chat": {
        "message": "user input text",
        "attachments": [
            {
            "src_resource_sha256": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1d0f",//用户端的原始文件
            "type": "image",
            }
        ],        
    }
    ...
}
```

其中：

```text
chat.message
```

只保存文本。

图片通过 attachment 引用。

---

# 7. ImageAsset

ImageAsset 表示上传成功后的图片文件。

建议：

```json
{
  "src_resource_sha256": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1d0f",
  "saved_resource_sha256": "3cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1d0f",
  "mime_type": "image/jpeg",
  "size": 183240,
  "width": 1280,
  "height": 1920,
  "storage_key": "session://$sessionId/$saved_resource_sha256",
  "created_at": "2026-08-12T14:00:00Z"
}
```

字段建议：

| Field       | Type     | Description        |
| ----------- | -------- | ------------------ |
| mime_type   | string   | MIME               |
| size        | integer  | bytes              |
| width       | integer  | pixels             |
| height      | integer  | pixels             |
| storage_key | string   | object storage key |
| created_at  | datetime | upload time        |

建议不要在 Message 中直接传 base64。

---

# 8. MessageAttachment

为了未来支持 PDF、Audio、Video：

```json
{
  "src_resource_sha256": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1d0f",
  "type": "image",
}
```

以后：

```text
image
file
audio
video
```

都可以使用同一种 attachment abstraction。

---

# 9. ImageAnalysis

ImageAnalysis 是 Vision Service 的核心输出。

建议：

```json
{
  "src_resource_sha256": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1d0f",
  "model": {
    "provider": "openrouter",
    "model": "xiaomi/mimo-v2.5"
  },
  "content_type": "english_exercise",
  "language": ["en"],
  "text": "I have lived here _____ 2019.\nA. for\nB. since...",
  "structured_content": {
    "type": "multiple_choice",
    "questions": [
      {
        "question": "I have lived here _____ 2019.",
        "options": [
          {"label": "A", "text": "for"},
          {"label": "B", "text": "since"},
          {"label": "C", "text": "during"},
          {"label": "D", "text": "from"}
        ]
      }
    ]
  },
  "knowledge_points": [],
  "created_at": "2026-08-12T14:00:01Z"
}
```

这里建议区分：

```text
text
```

和：

```text
structured_content
```

### text

尽可能接近图片中的原始文字。

### structured_content

面向业务的语义结构。

---

# 10. ImageAnalysis 的关键设计：不要让 Vision Service 输出业务答案

Vision Service 应该回答：

> 图片中有什么？

而不是：

> 用户应该怎么回答？

例如：

### Vision Service

```json
{
  "content_type": "english_exercise",
  "structured_content": {
    "question": "...",
    "options": [...]
  }
}
```

而不是：

```json
{
  "answer": "B",
  "explanation": "..."
}
```

后者属于 Agent Task Execution。

这样：

```text
Vision
  = Perception

Agent
  = Reasoning + Action
```

职责非常清楚。

---

# 12. Vision Service as LLM tools

为 Agent 提供一个 Vision Service 工具，输入参数 assert id， 输出 ImageAnalysis 。工具本身要有 timeout 机制 。Agent 结合 chat history 文本和 ImageAnalysis 在理解用户意图。

---

# 13. Agent 输入结构

Agent 最终拿到的是一个统一的 Context：

```python
class AgentInput:
    conversation_history: list[ChatMessage]

```

其中 ImageAnalysis 和 LearningTask 是 conversation context 的一个组成部分。

---

# 14. 前端 → 后端 API

建议不要让：

```text
POST /chat  (只是示例 path 不是设计或现状)
```

直接接收 base64 图片。

推荐两阶段设计。

## API 1：上传图片

Web/iphone app 前端提供前端 crop/orientation correction 的界面，用户完成 crop/orientation correction 后 ：

1. 计算修改后图片文件的 SHA256（如果用户没有实际修改操作，就用应该用原始图片来计算 sha256），作为 src_resource_sha256 。
2. 然后如果发现图片像素数大于 1920\*1200 时， 按比例缩放到最多  1920\* 1200 像素。
3. 上传

```http
POST /api/v1/images/2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1d0f  (只是示例 path 不是设计或现状)
Content-Type: multipart/form-data
```

Request：

```text
file=<binary>
```

Response：

```json
{
  "image": {
    "src_resource_sha256": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1d0f",
  	"saved_resource_sha256": "3cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1d0f", //   
    "mime_type": "image/jpeg",
    "width": 1280,
    "height": 1920,
    "size": 183240
  }
}
```



后端如果发现上传图片像素数大于 1920\*1200 时， 按比例缩放到最多  1920\* 1200 像素。然后计算调整后图片的 saved_resource_sha256 。

---

# 15. API 2：发送 Chat Message

```http
POST /api/v1/conversations/{conversation_id}/messages  (只是示例 path 不是设计或现状)
Content-Type: application/json
```

Request：

```json
{
    "schema_version": 1,
    "task": "none",
    "role": "user",
    "chat": {
        "message": "这道题为什么选 B？",
        "attachments": [
            {
            "src_resource_sha256": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1d0f",
            "type": "image",
            }
        ],        
    },
    "chat_context": {
        "resource_contexts": []
    },
    "source": {},
    "device": {}
}
```

这样设计有几个优势：

1. 图片和聊天解耦。
2. 可以上传图片后再发送。
3. 可以支持图片预览。
4. 可以支持多图片。
5. 可以重试 Chat 而不用重复上传。
6. 可以扩展其他附件。

---



# 19. Vision Service Interface

建议后端抽象：

```python
class VisionService(Protocol):

    async def analyze(
        self,
        image: ImageInput,
        *,
        purpose: VisionPurpose | None = None,
    ) -> ImageAnalysis:
        ...
```

实现：

```text
OpenRouterVisionService
```

内部使用：

```text
ChatOpenRouter
model=xiaomi/mimo-v2.5
```

以后可以增加：

```text
GeminiVisionService
OpenAIVisionService
AnthropicVisionService
```

Agent 不感知具体 provider。

---

# 20. Vision Purpose

为了避免每次都让模型完成所有任务，可以向 Vision Service 指定分析目的：

```text
ocr
exercise
document
learning_content
general
```

例如：

```python
analysis = await vision_service.analyze(
    image,
    purpose="exercise"
)
```

Prompt 可以因此更加专门。

---

# 21. Image Analysis Cache

推荐缓存。

相同：

```text
src_resource_sha256
+
vision_model
+
analysis_version
```

得到相同：

```text
ImageAnalysis
```

不需要重复调用 Vision Model。

Cache Key：

```text
src_resource_sha256
+
model
+
prompt_version
```

可以有效控制 OpenRouter 成本。

---

# 22. Agent 和 Vision 的两种调用模式

建议支持两个模式。

## 模式 A：Pre-analysis

```text
Upload
 ↓
Vision
 ↓
ImageAnalysis
 ↓
Agent
```



---

## 模式 B：Agent Tool

Agent 可以调用：

```text
analyze_image(src_resource_sha256)
```





# 29. Error Handling

至少定义：

```text
# Image Upload service
IMAGE_INVALID
IMAGE_TOO_LARGE
IMAGE_UNSUPPORTED
IMAGE_UPLOAD_FAILED

# Vision Service
VISION_ANALYSIS_FAILED
VISION_MODEL_UNAVAILABLE
VISION_OUTPUT_INVALID
```



内部日志保留：

```text
provider
model
request_id
image_id
analysis_id
conversation_id
trace_id
```



---

# 32. 安全与资源控制

图片是比普通文本更昂贵的输入，需要增加：

### 上传限制

```text
max file size
max resolution
allowed MIME
```

### 图片预处理

必要时：

```text
resize
compress
strip metadata
```

### 请求限制

例如：

```text
max images per message
max vision calls per message
max image megapixels
```

### 存储生命周期

明确：

```text
analysis retention
session retention
memory source retention
```



---

# 34. 推荐的实现顺序

研发实现建议按照以下顺序拆分：

```text
Phase 1
Image Upload
    ↓
ImageAsset
    ↓
MessageAttachment
```

```text
Phase 2
VisionService
    ↓
MiMo-V2.5
    ↓
ImageAnalysis
```

Phase 3 ...

