# Session

负责：
loop 阻塞等待 channel 消息，非调用 agent，把 agent 的响应转给 channel。

主要代码示例： `/src/everlingo/gateway/session.py`

## Session 属性
- id : Session 创建时自动生成。用 uuid string
- create_time: 创建时自动生成
- update_time: 最后一次会话的时间，有会话时更新
- title : 保留字段，默认为空，以后实现

## 持久化
Session 会话和 Agent 对话历史，暂时不需要支持持久化保存到文件。

## Channel
参考 [channel.md](/docs/impl-spec/channel.md)

## 消息循环

`Session.run()` 主循环：
```
channel.init()
while True:
    text = channel.recv()
    if text is None: break
    channel.send_typing_hint()
    replies = agent.invoke(MessageEvent(text=text))
    channel.stop_typing_hint()
    for r in replies:
        channel.send(r.text)
```

`agent.invoke()` 返回 `list[MessageEvent]`。当 LLM 在工具循环中产生多个
`AIMessage` 时（例如「翻译并朗读」），每条非空 `AIMessage.content` 作为独立
`MessageEvent` 返回，Session 逐条发送形成多个消息气泡。

详见 [agents-spec.md](/docs/impl-spec/agents-spec.md) — 多消息回复。