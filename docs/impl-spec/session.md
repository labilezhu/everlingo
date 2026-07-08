# Session

负责：
loop 从统一事件队列消费事件，调用 agent 处理，把 agent 的响应转给 channel。

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

## 事件队列模式（2026-07）

`Session.run()` 不再直接阻塞读取 channel，改为消费统一事件队列 `_event_queue`。
多个事件源（用户输入、系统通知）都会入队，由单消费者协程串行处理：

```
# _channel_listener（后台协程）
while True:
    text = channel.recv()
    if text is None: put(QuitEvent)
    else: put(UserMessage(text))

# run() 主循环
channel.init()
while True:
    ev = event_queue.get()
    if ev is QuitEvent: break
    if ev is UserMessage:
        typing_hint → agent.ainvoke → send replies
    if ev is SystemNotice:
        agent.ahandle_system_notice → send replies
```

### 事件类型

定义在 `src/everlingo/gateway/session_events.py`：

- `UserMessage(text)` — 来自 channel.recv() 的用户输入
- `SystemNotice(source, updated_files, update_summary, headword, lang)` — 后台系统通知
- `QuitEvent()` — channel 断开或用户退出

### 跨线程事件推送

`Session.post_event(ev)` 为线程安全入口，通过 `call_soon_threadsafe` 将事件入队。
Memory Writer Agent（全局单例 daemon thread）在写入成功后调用此方法推送通知。

### 通知处理

SystemNotice 走 `agent.ahandle_system_notice()`（LLM 中介），由 Chat Agent 根据用户偏好决定：
- 是否告知用户
- 告知时的详情程度（仅确认 / 读取 vault 文件给出详情）
- 用户未表达偏好时默认静默（回复空内容，不发消息）

通知轮**跳过** Memory Extract，因为知识已被 Writer 写入，重新抽取会重复。

详见：
- [chat-agent-spec.md](/docs/impl-spec/chat-agent-spec.md) — 多消息回复 / 系统事件通知
- [memory-writer-agent-spec.md](/docs/impl-spec/memory-writer-agent-spec.md) — 写入确认通知