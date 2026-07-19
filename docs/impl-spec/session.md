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
- `SystemNotice(source, updated_files, update_summary, title, lang)` — 后台系统通知
- `QuitEvent()` — channel 断开或用户退出

### 跨线程事件推送

`Session.post_event(ev)` 为线程安全入口，通过 `call_soon_threadsafe` 将事件入队。
Memory Writer Agent（全局单例 daemon thread）在**创建**笔记写入成功后调用此方法推送通知。

**delete/edit 不发通知**：笔记删除/编辑由 Chat Agent 的 `memory_writer_action` 工具同步调用，结果通过 `concurrent.futures.Future` 直接回传工具调用，不经过事件队列、不发 `SystemNotice`。详见 [memory-writer-agent-spec.md — 笔记删除与编辑](/docs/impl-spec/memory-writer-agent-spec.md#笔记删除与编辑同步-action-流程)。

### 通知处理

SystemNotice 走 `agent.ahandle_system_notice()`（LLM 中介），由 Chat Agent 根据用户偏好决定：
- 是否告知用户
- 告知时的详情程度（仅确认 / 读取 vault 文件给出详情）
- 用户未表达偏好时默认静默（回复空内容，不发消息）

通知轮**跳过** Memory Extract，因为知识已被 Writer 写入，重新抽取会重复。

详见：
- [chat-agent-spec.md](/docs/impl-spec/chat-agent-spec.md) — 多消息回复 / 系统事件通知
- [memory-writer-agent-spec.md](/docs/impl-spec/memory-writer-agent-spec.md) — 写入确认通知

## 交互日志

所有与用户交互的输入、输出文本，均在 `_handle_user_message` 与 `_handle_system_notice` 中以 `logger.debug` 记录，便于问题 debug。

日志前缀 `[ChatAgent]`，格式：

| 方向 | 前缀 | 示例 |
|------|------|------|
| 用户输入 | `[ChatAgent] IN` | `[ChatAgent] IN session=xxx channel=wechat text='hello'` |
| 系统通知输入 | `[ChatAgent] NOTICE IN` | `[ChatAgent] NOTICE IN session=xxx channel=wechat title=xxx files=...` |
| 回复输出 | `[ChatAgent] OUT` | `[ChatAgent] OUT[0] '回复文本'` |
| 通知回复输出 | `[ChatAgent] NOTICE OUT` | `[ChatAgent] NOTICE OUT[0] '通知回复'` |

OUT 先有一行 `OUT session=xxx channel=xxx replies=N` 记录回复条数，然后逐条 `OUT[i]` 记录每条文本内容。

日志 level 为 `debug`，需要将对应 logger（`everlingo.gateway.session`）的 level 调到 `DEBUG` 才能输出。