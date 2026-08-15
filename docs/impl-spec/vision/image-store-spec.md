# Image Store 图片存储设计文档

- 状态：Implemented（2026-08-15）
- 相关文档：
  - [ADR: 图片学习能力后端 High-Level Design](../../ADR/20260812-image-chat.md)
  - [Vision Service 设计文档](./vision-service-spec.md)
  - [Web Session Acceptor](../web-session-acceptor.md)
  - [Envelope 结构化用户输入协议](../envelope-impl-spec.md)

---

## 1. 背景

图片不直接进入业务 Agent（ADR §3.1），而是先由 Image Service 上传、存储为 `ImageAsset`，再在消息中经 `chat.attachments` 引用。原始图片字节与"图片理解结果"分离（ADR §3.2）：

```
ImageAsset          ChatMessage
   │                    │
   └── ImageAnalysis    └── references ImageAsset（src_resource_sha256）
```

本文档定义 Image Store 层的存储位置、上传端点契约、上传预处理与生命周期，是实现代码 `/src/everlingo/image/image_store.py` 与 `/src/everlingo/image/models.py` 的正式规范。

## 2. 数据模型

实现代码：`/src/everlingo/image/models.py`

### `ImageAsset`

| Field | Type | Description |
| --- | --- | --- |
| `src_resource_sha256` | string | 用户端原始文件 SHA-256（幂等上传键、Vision 缓存 key 组成部分） |
| `saved_resource_sha256` | string | 服务端处理后（EXIF 校正/缩放）字节的 SHA-256 |
| `mime_type` | string | MIME，允许 `image/jpeg` / `image/png` / `image/webp` |
| `size` | integer | 处理后字节数 |
| `width` | integer \| None | 处理后像素宽 |
| `height` | integer \| None | 处理后像素高 |
| `storage_key` | string | 逻辑存储键 `session://{session_id}/{saved_resource_sha256}` |
| `created_at` | datetime | 上传时间（UTC ISO8601） |

`src_resource_sha256` 与 `saved_resource_sha256` 分离的意义：
- `src` 是用户端原图标识，保证"幂等上传"与"分析结果复用"不受服务端预处理影响；
- `saved` 是服务端处理后落盘字节的标识。

### `MessageAttachment`

```python
class MessageAttachment(BaseModel):
    src_resource_sha256: str
    type: Literal["image"] = "image"
```

- 只携带 `src_resource_sha256`，不内联图片字节或分析结果。
- 为未来支持 `file` / `audio` / `video` 预留同一 attachment 抽象。
- 注意：live envelope 路径实际使用 `AttachmentPart`（`/src/everlingo/gateway/channels/envelope.py`），字段一致（`src_resource_sha256` + `type`）。两者并存，待后续统一。

## 3. 存储位置

物理落盘到本地文件系统：

```text
{workspace}/sessions/{session_id}/images/{saved_resource_sha256}.{ext}
```

- `{workspace}` 即 `workspace.current_workspace()`（默认 `~/.everlingo/workspaces/<name>/`，可经 `EVERLINGO_WORKSPACE_DIR` 覆盖），复用现有 workspace 模块，无需新增配置。
- `ImageAsset.storage_key` 存逻辑键 `session://{session_id}/{saved_resource_sha256}`；`ImageStore` 负责逻辑键 ↔ 物理路径映射。
- 当前为单进程部署，使用本地文件实现；未来换对象存储（S3/MinIO）只需替换 `ImageStore` 实现，调用方（上传端点、Vision Service）不变。

## 4. 前端 PUT 上传端点契约

```http
PUT /api/session/{session_id}/images/{src_resource_sha256}
Content-Type: multipart/form-data
```

### 请求

- 路径参数 `{session_id}`：图片归属的当前会话（与 `storage_key = session://{session_id}/{saved_sha}` 一致）。
- 路径参数 `{src_resource_sha256}`：客户端计算的原图 SHA-256。服务端会重新计算校验，不符则返回 400。
- multipart 字段 `file=<binary>`。

### 客户端前置要求

1. 前端提供 crop / orientation correction 界面，用户完成后计算修改后文件 SHA-256；若用户未实际修改，则用原始图片计算 SHA-256 作为 `src_resource_sha256`。
2. 若图片像素数大于 1920×1200，前端先行按比例缩放到最多 1920×1200 像素。

### 响应（成功后）

```json
{
  "image": {
    "src_resource_sha256": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1d0f",
    "saved_resource_sha256": "3cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1d0f",
    "mime_type": "image/jpeg",
    "width": 1280,
    "height": 1920,
    "size": 183240,
    "storage_key": "session://{session_id}/3cf24dba...",
    "created_at": "2026-08-12T14:00:00Z"
  }
}
```

### 错误语义

| 场景 | HTTP | detail |
| --- | --- | --- |
| 会话不存在 | 404 | `Session not found` |
| MIME 不在允许列表 | 415 | `Unsupported media type: {mime}` |
| 空文件 | 400 | `Empty file` |
| sha256 不匹配 | 400 | `sha256 mismatch` |
| 图片不可解析（Pillow 预处理失败） | 400 | `invalid image data` |

### 幂等

同一 `src_resource_sha256` 重复上传返回同一已注册 `ImageAsset`，不重复写盘、不改变元数据（`image_store.py` 内 `_registry` 去重）。

## 5. 上传预处理（Phase 2 新增，Pillow）

`ImageStore.save()` 在写盘前对字节做预处理（`preprocess_image()`），顺序为：

1. **EXIF 方向校正**：`ImageOps.exif_transpose()`，先按 EXIF orientation 摆正，避免后续 strip 后方向错乱。
2. **strip 元数据**：`img.copy()` + `img.info.clear()`，剥离 EXIF/文本块等隐私信息（JPEG 额外转 `RGB`。
3. **等比缩放**：像素数大于 `1920×1200`（`MAX_PIXELS`）时，按 `sqrt(1920*1200/(w*h))` 系数 LANCZOS 缩放。
4. **重算标识**：对处理后字节重新计算 `saved_resource_sha256`，填充 `width` / `height`，`size` 用处理后字节数。

要点：
- 预处理使 `saved_resource_sha256 != src_resource_sha256`（仅当图片需要处理时）。
- 缓存 key（见 [Vision Service 设计文档 — 缓存与并发防护](./vision-service-spec.md)）仍基于 **原始** `src_resource_sha256`，使同一原图无论保存形态都共享同一份分析。

### `ImageStore.read_bytes(src_resource_sha256) -> bytes | None`

由 `storage_key = session://{session_id}/{saved_sha}` 解析出物理路径并回读处理后的字节，供 Vision Service 编码 base64 data URI。未注册或物理文件缺失返回 `None`。

## 6. 资源限制（ADR §32）

| 项 | MVP 值 |
| --- | --- |
| max file size | 10 MB |
| max resolution | 1920×1200（超出按比例缩放） |
| allowed MIME | `image/jpeg`, `image/png`, `image/webp` |
| max images per message | 1（P1 放开多图） |

## 7. 错误映射（ADR §29）

| 错误码 | HTTP 状态 | 前端表现 |
| --- | --- | --- |
| `IMAGE_INVALID` / `IMAGE_UNSUPPORTED` | 415 | 上传失败，提示格式不支持 |
| `IMAGE_TOO_LARGE` | 413 | 上传失败，提示超过大小限制 |
| `IMAGE_UPLOAD_FAILED` | 500 | 上传失败，提示重试 |

内部日志保留：`request_id` / `image_id` / `conversation_id` / `trace_id`。

## 8. 存储生命周期

- **analysis retention**：LRU + TTL（7 天），与 session 解耦（见 Vision Service 缓存设计）。
- **session retention**：session 销毁即清理其 `ImageAsset` 存储（`storage_key` 归属对应 session）。
- **memory source retention**：若图片沉淀为 Memory，仅保留 `ImageAnalysis` 文本，原始图片按 session 生命周期处理。