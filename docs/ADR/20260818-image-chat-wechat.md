# Wechat Channel 图片接收与 LLM 分析

- 状态：Accepted（2026-08-18）
- 作者：engineering
- 相关文档：
  - [图片学习能力后端 High-Level Design](/docs/ADR/20260812-image-chat.md)
  - [聊天图片需求文档](/docs/ADR/20260812-image-chat-requirement.md)
  - [把聊天图片沉淀到笔记（Chat → Vault Image）](/docs/ADR/20260817-save-image-from-chat-to-note.md)
  - [Wechat(微信) 消息 Channel 实现规范](/docs/impl-spec/channel-wechat-ilink.md)
  - [Image Store 设计文档](/docs/impl-spec/vision/image-store-spec.md)
  - [Vision Service 设计文档](/docs/impl-spec/vision/vision-service-spec.md)
  - [Chat Agent 实现规范](/docs/impl-spec/chat-agent-spec.md)

实现后需回填的文档：
- `docs/impl-spec/channel-wechat-ilink.md`（「接收图片」节补实现说明：服务端下载 → `image_store.save` → envelope attachment）
- `docs/ADR/20260812-image-chat.md`（Phase 3 措辞「仅 web channel 且支持图片时」→「web / wechat channel 且支持图片时」）
- `TASKS.md`（记录改动）+ Release Notes

---

## 1. 背景与动机

[20260812-image-chat.md](/docs/ADR/20260812-image-chat.md) 完成了图片学习能力后端设计，并已落地 Phase 1–4，**但图片接收与 LLM 分析只在 Web Chatbot 上打通**：

- Web 流程：浏览器端算 SHA256 + 缩放 → `PUT /api/session/{id}/images/{sha}` 上传 → 后端 `image_store.save` → 前端构造带 `chat.attachments` 的 `UserInputEnvelope` → `POST /api/session/{id}/message` 发送。
- Agent 侧：`supported_image=True` 时自动注入 `analyze_image` 工具，由 Agent 经 `src_resource_sha256` 取 `ImageAnalysis`（ToolMessage 入历史）。

而 **Wechat Channel 目前 `recv_envelope` 只会 `wrap_plain_text(msg.text)`，直接丢弃 `msg.images`**（`wechat_channel.py:_handle_message`），既不上传图片、也不构造 attachment，更不会触发 Vision 分析。

需求要求补充 Wechat 的图片能力。难点在于：Wechat SDK 无法在「客户端」算 SHA / 上传（没有浏览器），只能在**服务端**复刻 web 的两阶段流程——但应尽量复用 web 已达成的底层模块，而非另写一套图片处理。

---

## 2. 现状关键事实（设计依据）

1. **Web 图片底层已是通用服务，不绑定 HTTP**：`image_store.save(session_id, src_resource_sha256, data, mime_type)`（`image_store.py:save`）内部统一完成：MIME 校验 → `sha256_of_bytes(data)` 重算并与入参比对 → `preprocess_image`（EXIF 校正 / strip 元数据 / 超限缩放）→ 落盘 `{workspace}/sessions/{session_id}/images/{saved_sha}.{ext}` → 注册 `ImageAsset`。Web 上传端点只是它的 HTTP 壳。`ImageStore` / `VisionService` 均为进程级单例，web 与 wechat 同处 gateway 进程，天然共享。
2. **Wechat SDK 收图方式是服务端下载**：`bot.download_raw(img.media, img.aes_key)`（`wechatbot/client.py:download_raw`）返回**原始加密 CDN 字节解密后的裸 bytes**，无 MIME / 文件名信息；`IncomingMessage.images: list[ImageContent]`（`wechatbot/types.py`），`ImageContent.media: CDNMedia` + `ImageContent.aes_key`（可为 `None`，下载时回落到 `media.aes_key`）。
3. **Channel → Agent 的接入点**：`WechatChannel.recv_envelope()` 返回 `UserInputEnvelope`，经 `Session._channel_listener` → `UserMessage` → `agent.ainvoke`。`ChannelMetadata.supported_image` 控制 Agent 是否注入 `analyze_image` 与 `copy_session_image_to_vault` 工具（`agent.py:_refresh_agent_if_needed`）。当前 `WechatChannel.get_metadata()` 未置 `supported_image`，故工具未注入。
4. **队列当前承载 `str`**：`wechat_channel.py` 的 `_queue: queue.Queue[Optional[str]]`，回调 `put(msg.text)`，`recv_envelope` `wrap_plain_text(text)`。要带 attachment 必须改为承载 envelope。
5. **`VisionService.analyze` 含单进程内 `in_flight: dict[cache_key, asyncio.Future]`**（`vision_service.py`）：`Future` 绑定到创建它的 event loop。若 Eager Warm 与目标 `analyze_image` 工具调用分处不同 event loop，会触发「awaiting future bound to a different loop」错误。因此**图片分析相关协程必须统一在同一 event loop 执行**（即 Session 的 asyncio loop，与 Agent 工具调用同 loop）。

---

## 3. 核心设计决策

### 决策 1：服务端复刻 web 两阶段流程，复用同一底层模块

Wechat 不新增图片处理逻辑，只是把「浏览器端做的下载 + 上传」搬到服务端：

```text
微信图片消息（bot 线程回调）
  → 提取 (text, image_refs) 入队（轻量描述，不下字节）
Session loop：recv_envelope 取出描述
  → await bot.download_raw(media, aes_key)        # 取原始字节
  → sniff_image_mime(data)                          # Pillow 嗅探 MIME
  → sha = sha256_of_bytes(data)                     # = src_resource_sha256
  → image_store.save(session_id, sha, data, mime)   # 复用 web 同一函数
  → envelope.chat.attachments = [AttachmentPart(src_resource_sha256=sha)]
  → asyncio.create_task(eager_warm(sha))            # 同 loop 预热（见决策 7）
  → 返回 envelope
Agent：supported_image=True → 注入 analyze_image → 经 sha 取 ImageAnalysis
```

复用边界：**web 与 wechat 共用 `image_store.save` / `sha256_of_bytes` / `preprocess_image` / `vision_service.analyze` / `eager_warm` / `make_vision_tool` / `make_copy_session_image_to_vault`**，仅「字节来源」与「envelope 构造位置」不同。

### 决策 2：图片处理统一在 Session loop 执行（避免跨 loop 的 Vision Future 错误）

- `on_message` 回调（运行在 bot 的专用线程 / event loop）**只做轻量动作**：保存 `_last_user_id`、把 `(text, images)` 包成内部 `_WechatIncoming` 入队。**不在回调里下载 / 存图 / 预热**（避免 Vision `Future` 创建在 bot loop）。
- 真正的下载、`image_store.save`、`eager_warm` 全部在 `recv_envelope` 内（Session loop）执行，与 Agent 的 `analyze_image` 工具调用处于**同一 event loop**，彻底规避 §2.5 的跨 loop `Future` 问题，且 Eager Warm 与 Tool Fetch 仍能按 [20260812-image-chat.md §23](/docs/ADR/20260812-image-chat.md) 正确合并并发。

### 决策 3：src_resource_sha256 = 下载原始字节的 SHA256

Web 的 `src_resource_sha256` 语义是「客户端原图 SHA」。Wechat 无客户端计算，故取**服务端下载得到的原始字节 SHA** 作为原图标识，传入 `image_store.save` 的 `src_resource_sha256`。`save` 内部会 `sha256_of_bytes(data)` 重算并比对——因我们用同一 `data` 计算，必然一致。`ImageAnalysis` 缓存键（§21）沿用该 `src_resource_sha256`，与 web 上传同一张原图时命中同一份缓存，跨用户/跨 channel 共享降本。

### 决策 4：MIME 嗅探（sniff_image_mime）

微信下载字节不带 MIME。新增模块级 `sniff_image_mime(data: bytes) -> str | None`（`image_store.py`）：用 `Image.open(BytesIO(data)).format` 映射 `JPEG→image/jpeg / PNG→image/png / WEBP→image/webp`，异常或未知格式返回 `None`。`None` 视为「不支持」（走决策 6 的失败处理）。与 `ALLOWED_MIME`（jpeg/png/webp）对齐 [20260812-image-chat.md §32](/docs/ADR/20260812-image-chat.md)。

### 决策 5：队列承载 envelope；抽取 `_build_envelope_from_message`

- `_queue` 类型从 `queue.Queue[Optional[str]]` 改为 `queue.Queue[Optional[UserInputEnvelope]]`；`_run` 收尾 `put(None)` 不变（None 仍表示 Channel 结束）。
- 图片下载 / 存图 / 构造 envelope 的逻辑抽到 `async def _build_envelope_from_message(self, msg) -> UserInputEnvelope`（在 Session loop 调用，便于单测：直接喂 fake `msg` + mock `bot`）。
- `on_message` 回调：`self._queue.put(_WechatIncoming(text=msg.text, images=msg.images))`（不再直接 `wrap_plain_text`）。
- `recv_envelope`：`item = await asyncio.to_thread(self._queue.get)`；`None`→`None`；否则 `return await self._build_envelope_from_message(item)`。

### 决策 6：失败与多图处理（对齐 ADR §32）

- **多图**：只取 `msg.images[:1]`（第一张），其余静默忽略（ADR §32 每消息最多 1 张图）。
- **下载失败 / MIME 不支持（sniff 返回 None）**：
  - 消息含文字 → **丢图、保留文字**（仍生成带文字、无 attachment 的 envelope，Agent 正常作答）。
  - 纯图片（无文字）→ **不生成空 turn**，经 `await self._bot.send(user_id, "暂时无法识别这张图片，请稍后再试或换个角度重新拍摄")` 回友好提示（失败静默，不抛异常中断）。
  - 两类失败均记 `logger.exception` 便于排查。

### 决策 7：Eager Warm 对齐 web（提取共享 `eager_warm`）

新增模块级 `async def eager_warm(src_resource_sha256: str) -> None`（`vision_service.py`），逻辑等同现有 `web_acceptor._eager_warm`（fire-and-forget，失败仅记日志）。`web_acceptor.py` 改为 import 复用（去重）；`wechat_channel` 在 `recv_envelope` 构造完带 attachment 的 envelope 后 `asyncio.create_task(eager_warm(sha))`（Session loop）。预热与 Agent 工具调用共用 [20260812-image-chat.md §21/§22](/docs/ADR/20260812-image-chat.md) 同一缓存，降低首响延迟。

### 决策 8：`get_metadata` 置 `supported_image=True`

`WechatChannel.get_metadata()` 增加 `supported_image=True`。效果（与 web 一致，由 `agent.py:_refresh_agent_if_needed` 门控）：
- 注入 `analyze_image` 工具 + Vision 提示词节；
- 同时注入 `copy_session_image_to_vault` 工具（[20260817 ADR 决策 4](/docs/ADR/20260817-save-image-from-chat-to-note.md) 同注入条件）→ Wechat 图片也能沉淀到笔记（预期增益，无需额外实现）。

---

## 4. 待回填到各 spec 文件的内容

> 以下片段在「实现完成后」回填；本 ADR 先记录目标内容，避免实现走样。

### 4.1 `docs/impl-spec/channel-wechat-ilink.md`「接收图片」节补实现说明

在「### 接收图片」SDK 示例后追加：

```text
## Wechat Channel 图片落地（实现说明）

ref: docs/ADR/20260818-image-chat-wechat.md
- bot.download_raw(img.media, img.aes_key) 取原始字节（img.aes_key 为 None 时回落 media.aes_key）。
- 服务端用 sniff_image_mime 嗅探 MIME（jpeg/png/webp），非支持格式按失败处理。
- src_resource_sha256 = sha256_of_bytes(下载字节)；调 image_store.save(session_id, sha, data, mime)
  复用与 Web 上传同一的落盘 / 预处理 / ImageAsset 注册逻辑。
- 构造带 chat.attachments 的 UserInputEnvelope；recv_envelope 内在 Session loop 调度 eager_warm。
- 多图取第一张；下载失败/格式不支持：有文字则丢图留字，纯图则回友好提示不生成空 turn。
- ChannelMetadata.supported_image=True 时 Agent 自动注入 analyze_image 与 copy_session_image_to_vault。
```

### 4.2 `docs/ADR/20260812-image-chat.md` Phase 3 措辞更新

原文「接入 MainAgent.build_tools（仅 web channel 且支持图片时）」改为「接入 MainAgent.build_tools（web / wechat channel 且支持图片时）」。并在 Phase 列表追加：

```text
## Phase 5（对齐 Wechat Channel）
WechatChannel 图片接收 + LLM 分析：
  ↓ _build_envelope_from_message（Session loop 下载 + image_store.save + attachment envelope）
  ↓ get_metadata.supported_image=True → 注入 analyze_image / copy_session_image_to_vault
  ↓ Eager Warm 对齐 web（eager_warm 共享函数）
```

---

## 5. 修改方案（文件级）

| 文件 | 改动 |
| --- | --- |
| `src/everlingo/image/image_store.py` | 新增 `sniff_image_mime(data: bytes) -> str \| None`（Pillow 读 format 映射 jpeg/png/webp） |
| `src/everlingo/image/vision_service.py` | 新增模块级 `async def eager_warm(src_resource_sha256: str) -> None`（与 web 上传预热同逻辑，失败仅记日志） |
| `src/everlingo/gateway/web_acceptor.py` | `upload_image` 改调用 `vision_service.eager_warm`（去重，删私有 `_eager_warm`） |
| `src/everlingo/gateway/channels/wechat_channel.py` | ① `_queue` 类型改 `Optional[UserInputEnvelope]`；② 构造参数新增 `session_id: str \| None = None`；③ 新增 `_WechatIncoming` 内部描述；④ 抽 `_build_envelope_from_message`（下载 + `sniff_image_mime` + `image_store.save` + 构造 envelope + `eager_warm`）、`_store_image`、`_safe_reply`；⑤ `on_message` 回调入队 `_WechatIncoming`；⑥ `recv_envelope` 消费并构造 envelope；⑦ `get_metadata` 加 `supported_image=True` |
| `src/everlingo/gateway/wechat_admin/runtime.py` | `start_wechat` 先 mint `session_id` 再 `WechatChannel(on_logined=..., session_id=session_id)`（兼容现有无参构造） |
| `docs/impl-spec/channel-wechat-ilink.md` | 「接收图片」节补 §4.1 实现说明 |
| `docs/ADR/20260812-image-chat.md` | Phase 3 措辞 + Phase 5 小节（§4.2） |
| `tests/test_wechat_channel.py` | 更新既有 2 处队列断言（入队 envelope）；新增图片用例：fake `bot.download_raw` 返回已知 PNG → `_build_envelope_from_message(fake msg(images=[ImageContent(media=...,aes_key=None)]))` → 断言 `attachments[0].src_resource_sha256 == 预期`、`image_store.get(sha)` 存在、`eager_warm` 被调度（mock `vision_service.analyze`）；新增失败用例（下载异常 / 非图片字节 → 无 attachment；纯图无文字 → 调用 `send` 友好提示） |
| `tests/test_image_store.py` | 新增 `sniff_image_mime` 用例（jpeg/png/webp 映射 + 非法字节返回 None） |
| `TASKS.md` + Release Notes | 记录改动 |

---

## 6. 测试要点

- **`sniff_image_mime`**：已知 JPEG/PNG/WEBP 字节 → 正确 MIME；损坏/未知格式 → `None`（不抛）。
- **`_build_envelope_from_message` 成功路径**：fake `bot.download_raw` 返回固定 PNG 字节 → envelope `chat.attachments[0].src_resource_sha256 == sha256_of_bytes(png)`；`image_store.get(sha)` 存在且 `mime_type=="image/png"`；`eager_warm` 被 `asyncio.create_task`（mock `vision_service.analyze` 验证会被调用，且调用上下文为 Session loop）。
- **多图**：`msg.images` 含 2 张 → envelope 仅 1 个 attachment。
- **失败 - 纯图**：`download_raw` 抛异常 或 返回非图片字节 → envelope 无 attachment，且 `_safe_reply` 经 `bot.send` 回了友好提示；不生成空 turn。
- **失败 - 有字丢图**：含文字 + 图片下载失败 → envelope 含文字 message、无 attachment（Agent 仍作答）。
- **`session_id` 注入**：runtime `start_wechat` 传入的 `session_id` 被 `_build_envelope_from_message` 用于 `image_store.save`（断言落盘路径含该 session_id）。
- **`supported_image`**：`get_metadata().supported_image is True`。
- **回归**：既有 `recv_envelope` 队列断言随队列类型变更更新；`test_run_retries_login_on_auth_error` 的 `put(None)` 收尾仍成立。

---

## 7. 风险与已知限制

- **队列类型破坏性变更**：`_queue` 从 `str` 改为 `UserInputEnvelope`，既有 2 个测试断言需同步更新（已在 §5/§6 覆盖）。
- **进程内存注册表**：`ImageStore._registry` 为进程内态，进程重启后无法取回（与 web 同限制，[20260817 ADR §7](/docs/ADR/20260817-save-image-from-chat-to-note.md) 已记录），可接受。
- **`supported_image=True` 自动增益**：开启后 Wechat 图片也获得 `copy_session_image_to_vault` 工具（可沉淀笔记）。属预期能力扩展，非回归；若暂不想对 Wechat 开放「存图到笔记」，可后续加 channel 级开关，本 ADR 默认一并开启以保持与 web 一致。
- **CDN 下载在 Session loop**：单会话串行，一次下载慢会短暂占用 Session loop；与 Agent 处理同序、同 loop，无并发问题。多会话各自独立 Session，互不阻塞。
- **跨 loop Vision Future**：已通过决策 2 规避（图片分析协程统一 Session loop）。

---

## 8. 设计取舍记录

- **否决**在 `on_message` 回调（bot loop）内下载 + 存图 + 预热：会让 `VisionService.analyze` 的 `in_flight` Future 创建在 bot loop，与 Agent 工具调用（Session loop）跨 loop，触发「awaiting future bound to a different loop」。改为回调只入队轻量描述，重活在 Session loop 完成。
- **否决**把 `msg` 原对象整体入队：耦合 SDK 类型；改为内部 `_WechatIncoming(text, images)`，解耦且便于单测。
- **否决** web / wechat 各写一套图片处理：违反「复用底层模块」原则；统一走 `image_store.save` + `eager_warm` 单例。
- **否决**为微信引入独立 SHA 计算入口（如缩略图 SHA）：与 web 的 `src_resource_sha256` 语义（原图 SHA）不一致，会导致同图跨 channel 缓存不共享；统一用下载原始字节 SHA。
- **否决**多图逐张拆成多轮 / 多图拒绝提示：与 ADR §32 单图限制和最简实现相悖；取第一张忽略其余。
