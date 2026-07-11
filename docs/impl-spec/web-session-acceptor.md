# Web Session Acceptor

首先，Web Session Acceptor，这是一个 [Session Acceptor](/docs/impl-spec/session-acceptor.md)。

启动时不会立即创建一个 Web Session。

需要增加一个 [Channel](/docs/impl-spec/channel.md) 的实现类 [WebChannel](/src/everlingo/gateway/channels/web_channel.py)

## 结构
Web Session Acceptor 的实现包括两部分：
- 后端，一个 uvicorn Web 服务器，它负责提供前端静态网页内容，以及一些动态的 FastAPI 的 API
- 前端

## 前端
参见 [Web Session UI](/docs/impl-spec/web-session-ui.md)

## 后端
FastAPI 的 API。

在收到用户输入的消息后，`WebChannel` 的 `async def recv(self) -> str` 方法返回消息文本内容给相关的 Session。

## 前后端协议

消息数据结构示例，请使用 pydantic 实现：
```python
class WebChatBotMessage:
    """Web 前后端协议消息体
    """

    # 消息正文
    text: str

    # 消息 id, 生成消息时，同时生成 uuid
    message_id: str = None

    # 消息相关的 session id
    session_id: str = None

    # 时间戳，生成消息的时间
    timestamp: datetime

    # 消息来源，webpage / server 枚举二选一
    from: str

    # 系统指令类型的消息。
    # 当 from=server 时，可以为： send / send_typing_hint / stop_typing_hint / send_sound
    command: str = None
```

### chatbot 服务端消息推送
chatbot 服务端消息推送数据采用 SSE(Server-Sent Events) 作为协议。会话需要有 session id 标识。

- 在 web_channel.py 的 `send_typing_hint`  `stop_typing_hint` `send` `send_sound` 被 Session 调用后，需要把相关的，推送到前端。
- `send_sound` 推送 `sound` 事件，`data` 含 `{ audio: <base64 mp3>, format: "mp3" }`，前端解码后渲染为独立语音气泡（含重听按钮，无需后端再次合成）。


## Session 超时回收

Web Session Acceptor 产生的 Session 需要有超时回收机制，防止用户断开后资源泄漏。

### 超时触发条件

`WebChannel.recv()` 使用轮询机制，每 `IDLE_CHECK_INTERVAL`（默认 30 秒）检查一次以下条件：

1. **DISCONNECT_GRACE**（无 SSE client 宽限期）：`len(self._sse_queues) == 0` 持续超过 `DISCONNECT_GRACE`（默认 5 分钟）→ `recv()` 返回 `None`
2. **ABSOLUTE_IDLE_TIMEOUT**（绝对空闲超时）：本次 `recv()` 调用以来无消息且超过 `ABSOLUTE_IDLE_TIMEOUT`（默认 60 分钟），即使有 SSE client → `recv()` 返回 `None`

### 退出流程

`recv()` 返回 `None` → `Session._channel_listener` 产生 `QuitEvent` → `Session.run()` 退出 → Gateway `_cleanup_session` 从 `sessions` 列表移除 → `web_acceptor` 的 done callback 从 `_channels` 移除。

### 日志

超时触发时，`WebChannel.recv()` 输出 info 日志（含 session id）：
- `session %s: DISCONNECT_GRACE timeout (no SSE client for %ds)`
- `session %s: ABSOLUTE_IDLE_TIMEOUT (idle %.0fs)`

`Session._channel_listener` 在产生 `QuitEvent` 时也输出 info 日志：`session %s: channel closed, posting QuitEvent`。
