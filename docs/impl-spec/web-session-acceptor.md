# Web Session Acceptor

首先，Web Session Acceptor，这是一个 [Session Acceptor](/docs/impl-spec/session-acceptor.md)。

启动时不会立即创建一个 Web Session。

需要增加一个 [Channel](/docs/impl-spec/channel.md) 的实现类 [WebChannel](/src/everlingo/gateway/channels/web_channel.py)

## 结构
Web Session Acceptor 的实现包括两部分：
- 后端，一个 uvicorn Web 服务器，它负责提供前端静态网页内容，以及一些动态的 FastAPI 的 API
- 前端

## 前端
有两种前端：
- [Standalone Web Chatbot](/docs/impl-spec/standalone-web-chatbot.md)
- [Chrome Extension — Web Sidecar](docs/impl-spec/chrome-extension-spec.md)

## 后端
FastAPI 的 API。

在收到用户输入的消息后，`WebChannel` 的 `async def recv_envelope(self) -> UserInputEnvelope | None` 方法返回结构化 `UserInputEnvelope`（详见 [envelope-spec.md](envelope-spec.md)）给相关的 Session。

## 前后端协议

前端通过 `POST /api/session/{session_id}/message` 发送用户输入。请求体为 union 格式（2026-07 起）：

**格式一：纯文本（兼容旧前端）**
```json
{"text": "想翻译的文本"}
```
后端自动包装为最小 `UserInputEnvelope`（`task=none`, `source.kind=plain`）。

**格式二：结构化 envelope（新前端）**
```json
{
  "envelope": {
    "schema_version": 1,
    "task": "translate",
    "chat": {"message": "为什么这里不是银行？"},
    "selection": {"text": "bank"},
    "context": {"text": "I sat on the bank of the river."},
    "source": {"kind": "web", "url": "https://..."},
    "device": {"platform": "chrome_ext", "locale": "zh-CN"}
  }
}
```

### chatbot 服务端消息推送
chatbot 服务端消息推送数据采用 SSE(Server-Sent Events) 作为协议。会话需要有 session id 标识。

- 在 web_channel.py 的 `send_typing_hint`  `stop_typing_hint` `send` `send_sound` 被 Session 调用后，需要把相关的，推送到前端。
- `send_sound` 推送 `sound` 事件，`data` 含 `{ audio: <base64 mp3>, format: "mp3" }`，前端解码后渲染为独立语音气泡（含重听按钮，无需后端再次合成）。


## CORS 配置

扩展前端（origin = `chrome-extension://<id>`）请求后端 API 属于跨源。`web_acceptor.py` 根 `FastAPI()` 应用挂载了 FastAPI 内置的 CORSMiddleware：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)
```

- MVP 使用 `allow_origins=["*"]`（不涉及 cookie/credentials，合规）。
- 生产前应收敛到白名单（列出已知扩展 ID 或使用 `allow_origin_regex`）。
- CORSMiddleware 自动处理 OPTIONS 预检请求（返回 200 + CORS 头），因此无需在路由层额外注册 OPTIONS handler。


## Session 超时回收

Web Session Acceptor 产生的 Session 需要有超时回收机制，防止用户断开后资源泄漏。

### 超时触发条件

`WebChannel.recv()` 使用轮询机制，每 `IDLE_CHECK_INTERVAL`（默认 30 秒）检查一次以下条件：

1. **DISCONNECT_GRACE**（无 SSE client 宽限期）：`len(self._sse_queues) == 0` 持续超过 `DISCONNECT_GRACE`（默认 20 分钟）→ `recv()` 返回 `None`
2. **ABSOLUTE_IDLE_TIMEOUT**（绝对空闲超时）：本次 `recv()` 调用以来无消息且超过 `ABSOLUTE_IDLE_TIMEOUT`（默认 60 分钟），即使有 SSE client → `recv()` 返回 `None`

### 退出流程

`recv()` 返回 `None` → `Session._channel_listener` 产生 `QuitEvent` → `Session.run()` 退出 → Gateway `_cleanup_session` 从 `sessions` 列表移除 → `web_acceptor` 的 done callback 从 `_channels` 移除。

### 日志

超时触发时，`WebChannel.recv()` 输出 info 日志（含 session id）：
- `session %s: DISCONNECT_GRACE timeout (no SSE client for %ds)`
- `session %s: ABSOLUTE_IDLE_TIMEOUT (idle %.0fs)`

`Session._channel_listener` 在产生 `QuitEvent` 时也输出 info 日志：`session %s: channel closed, posting QuitEvent`。
