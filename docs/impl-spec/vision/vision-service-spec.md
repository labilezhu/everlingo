# Vision Service 图片理解设计文档

- 状态：Implemented（2026-08-15）
- 相关文档：
  - [ADR: 图片学习能力后端 High-Level Design](../../ADR/20260812-image-chat.md)
  - [Image Store 图片存储设计文档](./image-store-spec.md)
  - [Chat Agent 设计文档](../chat-agent-spec.md)
  - [Chat Agent Tools 设计文档](../chat-agent-tools-spec.md)

---

## 1. 职责边界

Vision Service 只做 **感知（Perception）**，回答"图片里有什么"；推理与行动（解答、讲解、步骤）由 Agent 负责。因此：

- Vision 输出 `ImageAnalysis`（OCR 文本 + 业务语义结构），**绝不**输出 `answer` / `explanation`。
- Agent 获取图片理解结果的**唯一路径**是调用 Vision Service 提供的 LLM 工具 `analyze_image`（ADR §12 / §10）。

实现代码：`/src/everlingo/image/vision_service.py`

## 2. 数据模型

### `ImageInput`

```python
class ImageInput(BaseModel):
    src_resource_sha256: str
```

Vision 分析的输入引用。VisionService 据此从 `ImageStore.read_bytes()` 读回字节。Phase 2 仅承载 `src_resource_sha256`，未来扩展到多图/混合资源时在此扩展字段。

### `ImageAnalysis`（Vision Service 核心输出）

| Field | Type | Description |
| --- | --- | --- |
| `src_resource_sha256` | string | 原图标识（也是缓存 key 组成部分） |
| `model` | dict | `{"provider": "...", "model": "..."}` |
| `content_type` | string | 内容类型（ex: `english_exercise` / `document` / `ocr` / `general`） |
| `language` | list[string] | 图片中语言代码，如 `["en"]` |
| `text` | string | 尽量接近原图的文字（OCR 层） |
| `structured_content` | dict | 面向业务的语义结构（理解层）；宽松 dict |
| `knowledge_points` | list[string] | 知识点标签数组 |
| `created_at` | string | UTC ISO8601 |

`text` 与 `structured_content` 分离：前者贴近原始文字，后者面向业务语义。

`structured_content` 的形态随 `content_type` 化（选择题 / 文档 / 单词卡 / …），Phase 2 用**宽松 `dict[str, Any]`** 容纳，不绑死单一 schema；后续可按 `content_type` 细化强类型 schema。


示例：
```json
{
    "src_resource_sha256": "ee9a17fb9ff1e6539b760124a134bed7a1942640d602e70a868afb6bd49e1144",
    "model": {
        "provider": "openrouter",
        "model": "xiaomi/mimo-v2.5"
    },
    "content_type": "english_exercise",
    "language": [
        "en",
        "zh"
    ],
    "text": "9:22 duolingo\n输入所缺单词\nIs the ______ good for your schedule?\ntime\n正确答案是： Is the timing good for your schedule?\n知道了",
    "structured_content": {
        "type": "general"
    },
    "knowledge_points": [],
    "created_at": "2026-08-15T14:01:48.243375+00:00"
}
```

### `VisionPurpose`

```text
ocr | exercise | document | learning_content | general
```

Vision 分析目的，用于让模型 prompt 更专项（ADR §20）。序列化为原始字符串（`str` Enum）。

## 3. VisionService 接口

### 抽象

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

Agent / 上层不感知具体 provider。

### 实现：`OpenRouterVisionService`

- 内部使用 `ChatOpenAI`（OpenRouter，`create_vision_llm()`），默认 `model = xiaomi/mimo-v2.5`。
- 调用流程：
  1. `ImageStore.get()` + `read_bytes()` 取处理后的图片字节；
  2. 编码为 `data:{mime};base64,{b64}` data URI；
  3. 按 `purpose` 拼专项 system prompt，消息体含 `image_url` content part；
  4. `await llm.ainvoke(messages)`；
  5. 提取响应 JSON（容忍 markdown 代码块）→ 构造 `ImageAnalysis`。
- 未来可增加 `GeminiVisionService` / `OpenAIVisionService` / `AnthropicVisionService`。

## 4. 配置

### `vision_model`

优先级：`setting.sys_setting.vision_model` > env `VISION_MODEL` > 默认 `xiaomi/mimo-v2.5`。
`get_vision_llm_config()`（`/src/everlingo/config.py`）复用 chat LLM 的 `openai_api_key` / `openai_base_url`（默认 OpenRouter），仅 model 独立。

### `create_vision_llm()`

`/src/everlingo/llm.py`：`temperature=0`（结构化确定性）、`request_timeout=120`（Vision 超时兜底）。

## 5. 缓存与并发防护（ADR §21 / §23）

`OpenRouterVisionService` 维护两个进程内结构：

```python
persistent_cache: dict[cache_key, (ts, ImageAnalysis)]   # LRU + TTL
in_flight:        dict[cache_key, asyncio.Future[ImageAnalysis]]
```

`analyze()` 逻辑（cache-first）：

1. 命中 `persistent_cache` 且未过期 → 直接返回；
2. 已在 `in_flight` → `await` 同一 Future（合并所有并发调用方，含 Eager Warm 与 Agent 工具）；
3. 否则创建 Future → 调 Vision Model → 写缓存 → 清 `in_flight`；任一异常同样从 `in_flight` 移除并向上传播。

保证：无论 Eager Warm 还是 Agent 工具、无论几次并发，对同一 key 的 Vision Model 调用**至多一次**。

### Cache Key

```text
{src_resource_sha256}|{model}|v{prompt_version}|{purpose or "general"}
```

> 实现注记（与 ADR §21 字面的差异）：ADR §21 字面 key 为 `src + model + prompt_version`；实际实现额外追加了 `purpose` 段。原因：§20 的 `purpose` 影响 prompt → 影响分析结果，若不纳入 key 会串缓存。当前 MVP 调用方（Eager Warm、`analyze_image` 工具）均默认 `general`，含 purpose 仅为未来细分预留正确性，不影响成本控制。

- `persistent_cache`：LRU（`MAX_CACHE_SIZE=256`）+ TTL（`CACHE_TTL_SECONDS=7 天`），跨用户全局共享（缓存内容是 `ImageAnalysis` 文本，不含用户身份/私有元信息，无隐私泄露风险）。
- 部署范围：单 uvicorn 进程内存实现；多 worker 横向扩展需将两结构替换为共享存储（如 Redis），留作 P1。

## 6. Agent 调用模式：混合（ADR §22）

### Eager Warm（上传即预热）

- 触发点：图片上传存储成功后（`web_acceptor.py`），`asyncio.create_task` 异步触发 `vision_service.analyze(...)`。
- 行为：fire-and-forget、非阻塞、失败静默（不阻塞 200，不影响上传成功）。
- 收益：用户在"上传 → 按发送"的输入间隙把缓存填上，Agent 首次调工具大多命中缓存，首响延迟低。

### Tool Fetch（cache-first）

- Agent 始终经 `analyze_image` 工具取用结果，不直接拿分析结果。
- 工具后端走 `VisionService.analyze()` 的 cache-first 逻辑（与 Eager Warm 共用同一缓存）。

两条路径共用同一缓存，无重复分析。

## 7. `analyze_image` Agent 工具

实现代码：`/src/everlingo/tools/vision_tool.py`（工厂 `make_vision_tool(service)`，与 `make_memory_writer_action_tool` 同模式）。

```python
# args_schema
class _AnalyzeImageArgs(BaseModel):
    src_resource_sha256: str  # 来自 envelope.chat.attachments[].src_resource_sha256
```

- 调用 `service.analyze(ImageInput(src_resource_sha256=...))`，返回 `ImageAnalysis.model_dump_json()` 字符串，作为 **ToolMessage** 落入消息历史（标准 tool-call 模式，不经 envelope / XML 注入）。
- Agent 只持有 `src_resource_sha256`，不直接持有原始图片字节或分析结果，按需经工具取用（ADR §12）。

### 注册门控

- `ChannelMetadata.supported_image`（`/src/everlingo/gateway/channels/channel.py`）标识通道是否支持图片；web 通道置 `True`。
- `MainAgent._refresh_agent_if_needed()`（`/src/everlingo/agents/agent.py`）仅在 `supported_image` 时把 `analyze_image` 注册进工具列表，并在 system prompt 注入"图片理解能力"段落。
- 对齐 ADR："仅 web channel 且支持图片时"。

### 错误降级（ADR §29）

`analyze_image` 工具在 Vision 分析失败时（`VisionServiceError` 及其子类）**返回结构化错误提示**而非抛异常中断会话：

```text
抱歉，我暂时无法识别这张图片，请稍后再试或换个角度重新拍摄。（VISION_xxx）
```

Agent 收到后以自然语言友好转告用户，不返回空答案或崩溃。

## 8. 错误码（ADR §29）

| 错误码 | 场景 | HTTP 状态 | 前端/工具表现 |
| --- | --- | --- | --- |
| `VISION_MODEL_UNAVAILABLE` | LLM 构造失败（配置/API Key 缺失等） | 502 / 200(tool) | 上传已成功；工具返回错误 → Agent 友好降级 |
| `VISION_ANALYSIS_FAILED` | Vision 模型调用失败 | 502 / 200(tool) | 同上 |
| `VISION_OUTPUT_INVALID` | 模型输出非 JSON / 缺字段 | 502 / 200(tool) | 同上 |

内部日志保留：`provider` / `model` / `request_id` / `image_id` / `analysis_id` / `conversation_id` / `trace_id`。

## 9. 实现状态

- **Phase 2（Done）**：VisionService（`OpenRouterVisionService`）+ `ImageAnalysis`（text + structured_content）+ 持久缓存/`in_flight` 并发防护 + 上传后 Eager Warm（引入 Pillow 缩放/EXIF 校正）。
- **Phase 3（Done）**：`make_vision_tool` 工厂 → `MainAgent` 注册（`supported_image` 门控）→ `analyze_image(src_sha) -> ToolMessage` → 错误降级。

P1 待办：多图片、Vision Purpose 细分、分布式并发防护、per-user vision 配额、PDF/音频等其它 attachment 类型。