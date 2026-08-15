# EverLingo 图片学习能力后端 High-Level Design

相关文档：

- docs/impl-spec/chat-agent-spec.md
- src/everlingo/agents/spec/envelope_spec.md
- docs/ADR/20260812-image-chat-requirement.md

ADR 实现后更新到文档：

- docs/impl-spec/vision/vision-service-spec.md
- docs/impl-spec/vision/image-store-spec.md


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

Agent 获取图片理解结果的**唯一路径**是调用 Vision Service 提供的 LLM 工具：

```python
analyze_image(src_resource_sha256: str) -> ImageAnalysis
```

- 输入：图片的 `src_resource_sha256`（来自 envelope 的 `chat.attachments`）。
- 输出：`ImageAnalysis`（见 §9），作为 **ToolMessage** 进入 LangChain 消息历史（标准 tool-call 模式，不通过 envelope / XML 注入）。
- Agent 只持有 `src_resource_sha256`，**不直接持有原始图片字节或分析结果**，按需经工具取用。
- 工具本身要有 timeout 机制（见 §29 错误处理）。
- Agent 结合 `chat history` 文本与 `ImageAnalysis` 理解用户意图；当消息仅含 attachments 而无文本时，不触发"延续上一轮话题"语义。

---

# 13. Agent 输入结构

Agent 最终拿到的是一个统一的 Context：

```python
class AgentInput:
    conversation_history: list[ChatMessage]
```

其中 `ImageAnalysis` 与 `LearningTask` 是 conversation context 的组成部分，但**不是**直接塞进消息文本。图片场景下的接入方式为：

- 用户消息的 envelope 携带 `chat.attachments[].src_resource_sha256`（仅引用，不含分析结果）。
- Agent 在需要理解图片时调用 `analyze_image(src_resource_sha256)` 工具。
- 工具返回的 `ImageAnalysis` 以 **ToolMessage** 形式落到本轮消息历史，后续 LLM 推理直接消费该 ToolMessage。
- 这样保持 Agent 输入仍是 `conversation_history: list[ChatMessage]`，Vision 结果作为标准 tool 结果存在，无需额外的 XML 注入通道。

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
PUT /api/session/{session_id}/images/{src_resource_sha256}
Content-Type: multipart/form-data
```

> 路径中 `{session_id}` 用于把图片归属到当前会话（与 `storage_key = session://{session_id}/{saved_resource_sha256}` 一致）；`{src_resource_sha256}` 为客户端计算的原图 SHA256，服务端会重新计算校验，不符则返回 400。该路径为实际设计（非示例）。

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

### 存储位置

图片字节落盘到本地文件系统：

```text
{workspace}/sessions/{session_id}/images/{saved_resource_sha256}.{ext}
```

- `{workspace}` 即 `workspace.current_workspace()`（默认 `~/.everlingo/workspaces/<name>/`，可经 `EVERLINGO_WORKSPACE_DIR` 覆盖），复用现有 workspace 模块，无需新增配置。
- `ImageAsset.storage_key` 存逻辑键 `session://{session_id}/{saved_resource_sha256}`；`ImageStore` 负责逻辑键 ↔ 物理路径的映射。
- 当前为单进程部署，使用本地文件实现；未来换对象存储（S3/MinIO）只需替换 `ImageStore` 实现，调用方（上传端点、Agent 工具）不变。

### 上传后异步预热（Eager Warm）

图片存储成功后，后端**不阻塞 200 响应**，以 `asyncio.create_task`（或后台队列）异步触发：

```python
await VisionService.analyze(key)   # fire-and-forget，预热 Vision 缓存
```

- 预热失败（Vision 模型不可用 / 超时）**静默处理**，不影响上传成功；Agent 后续经 `analyze_image` 工具调用时会重新触发分析（见 §22 / §23）。
- 预热目的是：用户上传到按"发送"之间通常有几秒输入时间，预热能让 Agent tool 调用命中缓存、降低首响延迟。
- eager 预热计入 per-user vision 调用（暂不设上限；成本由 Vision Service 统一管控）。

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

> 实现注记（Phase 2）：实际 cache key 还追加了 `purpose` 段
> （`{src_resource_sha256}|{model}|v{prompt_version}|{purpose or "general"}`）。
> 目的：§20 的 purpose 会影响 prompt → 影响分析结果，若不纳入 key，不同 purpose
> 的分析会互相串缓存。当前 MVP 调用方（Eager Warm、analyze_image 工具）均默认 general，
> 含 purpose 仅是为未来细分预留正确性，不影响成本控制。

可以有效控制 OpenRouter 成本。

### 全局共享缓存（跨用户）

缓存按 Cache Key 全局共享（不区分用户）。理由：

- 热门学习图片（如同一道英语题、同一篇公开文章）可能被多个用户上传，命中缓存可显著降本。
- 缓存内容是 **ImageAnalysis 文本**（OCR 文本 + 结构化语义），不含任何用户身份或私有元信息，跨用户复用无隐私泄露风险。
- 手写笔记、私人错题等虽然不同用户内容不同，但 sha256 不同 → key 自然隔离，不会串档。

### Eager 预热与 Tool 取用共用同一缓存

上传时的异步预热（§14）与 Agent 经 `analyze_image` 工具取用（§22）都调用同一个 `VisionService.analyze(key)` 入口，读写同一个缓存。预热命中时工具调用直接返回，零额外 Vision 成本。

---

# 22. 图片理解的调用模式：上传预热 + 工具取用（混合模式）

不采用"模式 A / 模式 B 二选一"，而是将两者优势结合的**混合模式**：

```text
PUT /api/v1/images/{sha256}
   └─ 存储 ImageAsset
        └─ fire-and-forget: asyncio.create_task(VisionService.analyze(key))   ← Eager Warm（预热缓存，不阻塞 200）

用户发送消息（envelope.chat.attachments[].src_resource_sha256）
   └─ Agent 调用 analyze_image(src_resource_sha256) 工具
        └─ VisionService.analyze(key):
             1) 命中持久缓存 → 返回
             2) 已在 in_flight → await 同一 Future（合并并发，见 §23）
             3) 否则建 Future → 跑 Vision Model → 写缓存 → 清 in_flight
         → ImageAnalysis 作为 ToolMessage 进入消息历史
```

## Eager Warm（上传即预热）

- 触发点：图片上传存储成功后（§14）。
- 行为：异步、非阻塞、失败静默；目的是在用户"上传 → 按发送"的输入间隙把缓存填上。
- 收益：Agent 首次调 `analyze_image` 时大多已命中缓存，首响延迟低。

## Tool Fetch（cache-first）

- Agent 始终经 `analyze_image` 工具取用图片理解结果，不直接拿分析结果。
- 工具后端走 `VisionService.analyze(key)` 的 cache-first 逻辑。
- 收益：
  - Agent 可自主决定是否分析（如用户只发图但说"你好"，Agent 可不调工具）。
  - 缓存命中时零 Vision 成本。
  - 两条路径共用缓存，无重复分析。

## 与早期方案的关系

- 早期"模式 A：Pre-analysis"≈ 本模式的 Eager Warm 部分。
- 早期"模式 B：Agent Tool"≈ 本模式的 Tool Fetch 部分。
- 本模式用 Eager Warm 解决"Agent 看不到图就要决定是否分析"的鸡生蛋问题，用 Tool Fetch 保留 Agent 的取用主权与成本可控性。

---

# 23. 并发分析防护（Concurrency Guard）

同一 `src_resource_sha256` 不应被重复分析：既有多用户上传同一图片（全局缓存命中后即无重复），也有**同一会话内** Eager 预热与 Agent tool 调用、或多个并发 tool 调用对同一 sha256 竞态。

## 单进程内存实现（MVP）

`VisionService` 维护两个结构：

```python
persistent_cache: dict[cache_key, ImageAnalysis]          # LRU / TTL，跨请求持久
in_flight:        dict[cache_key, asyncio.Future[ImageAnalysis]]  # 仅本进程运行期内
```

`analyze(key)` 逻辑：

1. `key` 命中 `persistent_cache` → 直接返回。
2. `key` 已在 `in_flight` → `await` 同一个 Future（合并所有并发调用方，含 Eager 预热与 Agent tool）。
3. 否则创建 `Future`，调用 Vision Model，成功后写入 `persistent_cache` 并从 `in_flight` 移除；任一异常也需从 `in_flight` 移除并向上传播。

该设计保证：无论 Eager 预热还是 Agent 工具、无论几次并发，对同一 key 的 Vision Model 调用**至多一次**。

## 部署范围

当前为单 uvicorn 进程部署，内存 `in_flight` 足够。若未来多 worker 横向扩展，需将 `in_flight` 与 `persistent_cache` 替换为共享存储（如 Redis 分布式锁 + 共享缓存），留作 P1。

---

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

### Agent 工具降级

`analyze_image` 工具在 Vision 分析失败时（命中 `VISION_*` 错误）应向 Agent 返回结构化错误而非抛异常中断会话。Agent 收到错误后应以自然语言友好提示（如"抱歉，我暂时无法识别这张图片，请稍后再试或换个角度重新拍摄"），而不是返回空答案或崩溃。

错误码到 HTTP 状态的建议映射（供 `web_acceptor.py` 上传接口与工具接口统一）：

| 错误码 | HTTP 状态 | 前端/工具表现 |
|---|---|---|
| `IMAGE_INVALID` / `IMAGE_UNSUPPORTED` | 415 | 上传失败，提示格式不支持 |
| `IMAGE_TOO_LARGE` | 413 | 上传失败，提示超过大小限制 |
| `IMAGE_UPLOAD_FAILED` | 500 | 上传失败，提示重试 |
| `VISION_MODEL_UNAVAILABLE` / `VISION_ANALYSIS_FAILED` / `VISION_OUTPUT_INVALID` | 502/200(tool) | 上传成功；工具返回错误，Agent 友好降级 |

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

### 上传限制（MVP 建议值）

```text
max file size: 10 MB
max resolution: 1920 x 1200（超出按比例缩放，见 §14）
allowed MIME: image/jpeg, image/png, image/webp
```

### 图片预处理

必要时：

```text
resize
compress
strip metadata（须先应用 EXIF orientation 校正再 strip，避免方向错乱）
```

### 请求限制（MVP 建议值）

例如：

```text
max images per message: 1（P1 放开多图）
max vision calls per message: 1
max image megapixels: 2.3（1920x1200）
```

### Vision 调用配额

- Eager 预热与 Agent tool 触发的 Vision 分析**统一计入 per-user vision 调用配额**（MVP 暂不设额外上限，由 Vision Service 统一管控成本；P1 再加 per-user / per-day 限额防止滥用）。
- 同一 `src_resource_sha256` 因并发防护（§23）与全局缓存（§21）保证不会重复计费。

### 存储生命周期

明确：

```text
analysis retention: LRU + TTL（如 7 天），与 session 解耦
session retention: session 销毁即清理其 ImageAsset 存储（见 §5 storage_key）
memory source retention: 若图片沉淀为 Memory，仅保留 ImageAnalysis 文本，原始图片按 session 生命周期处理
```



---

# 34. 推荐的实现顺序

研发实现建议按照以下顺序拆分：

## Phase 1 — 前后端最小闭环（不含 Vision 理解）: Done
后端：
  PUT /api/session/{session_id}/images/{src_resource_sha256}  (multipart)
    ↓
  ImageStore（落盘 {workspace}/sessions/{session_id}/images/）
    ↓
  ImageAsset + MessageAttachment 数据模型
    ↓
  envelope.chat.attachments 字段打通（Agent 暂不透传消费）
前端：
  ChatInput 选图/粘贴/预览/删除 + 发送前 uploadImage
    ↓
  用户气泡渲染已上传图片（URL.createObjectURL，Phase 1 不新增 GET 回取端点）
验收：上传→气泡显示→envelope 带 attachments→后端存图→同图幂等
注：Phase 1 不做缩放/EXIF（无 Pillow，saved==src）；单图限制（max 1/消息）

## Phase 2: Done

VisionService (OpenRouterVisionService, model=xiaomi/mimo-v2.5)
    ↓
ImageAnalysis（text + structured_content）
    ↓
持久缓存 + in_flight 并发防护（§21 / §23）
    ↓
上传后 Eager Warm（§14，已引入 Pillow 做缩放/EXIF 校正）
注：purpose 默认 general；结构化输出走宽松 dict，未绑定单一 schema。

## Phase 3: Done

Vision Tool: make_vision_tool(service, ...)（与 make_memory_writer_action_tool 同模式）
    ↓
接入 MainAgent.build_tools（仅 web channel 且支持图片时）
    ↓
analyze_image(src_resource_sha256) -> ToolMessage
    ↓
错误降级（§29）

## Phase 4（对齐需求 P0 "Memory"）
图片场景下的 request_memory_extraction 衔接：
    ↓
entries.conversation_context 引用 ImageAnalysis（id 或嵌入 text），沉淀为 Note / Memory

P1 另含：多图片、Vision Purpose 细分（§20）、分布式并发防护、per-user vision 配额、PDF/音频等其它 attachment 类型。

