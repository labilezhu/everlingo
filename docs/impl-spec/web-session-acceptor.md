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




