# Web Session Acceptor

首先，Web Session Acceptor，这是一个 [Session Acceptor](/docs/impl-spec/session-acceptor.md)。

启动时不会立即创建一个 Web Session。

需要增加一个 [Channel](/docs/impl-spec/channel.md) 的实现类 [WebChannel](/src/everlingo/gateway/channels/web_channel.py)

## 结构
Web Session Acceptor 的实现包括两部分：
- 后端，一个 uvicorn Web 服务器，它负责提供前端静态网页内容，以及一些动态的 FastAPI 的 API
- 前端

## 前端
Web 前端给用户，一个 Chatbot 的聊天界面。支持 markdown 格式消息的渲染。

成功连接 Chatbot 后端后，session id 将作为前后端建立连接时的标识。

前端技术选型： Vite + React。

前端代码，静态网页文件位于目录 /web 中。

### Chatbot 界面设计
一个经典的 chatbot 聊天对话框。聊天机器人的名字叫：小记🐹 

消息内容主要是 markdown 文本，markdown 文本消息需要在界面渲染。

界面需要有动态元素提示：
- `小记🐹正在思考`

- 在收到后端推送的 `send_typing_hint` 后，显示`小记🐹正在思考`。在收到后端推送的 `stop_typing_hint` 后，不再显示 `小记🐹正在思考`。
- 在收到后端的 `send` 


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
    # 当 from=server 时，可以为： send / send_typing_hint / stop_typing_hint
    command: str = None
```

### chatbot 服务端消息推送
chatbot 服务端消息推送数据采用 SSE(Server-Sent Events) 作为协议。会话需要有 session id 标识。

- 在 web_channel.py 的 `send_typing_hint`  `stop_typing_hint` `send` 被 Session 调用后，需要把相关的，推送到前端。




