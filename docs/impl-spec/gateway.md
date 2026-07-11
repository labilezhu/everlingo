# Gateway

一个独立的 python 进程。

负责：
- 按启动参数要求，创建相应的 `Session Acceptor` 。
- 维护和管理一个 `Session 列表`。Session 用 session id 标识
- 接收和处理来自 `Session Acceptor` 的 `session 创建请求`。
- 接收后台 Agent（Memory Writer 等）的系统通知并路由到对应 Session。
  
## `session 创建请求` 的处理
为 Channel 实例，建立专用的 Agent 实例。并把这种 Channel 实例 与 Agent 实例的绑定，封装为一个 Session 对象。

Gateway 收到 `session 创建请求` 时，一般需要**创建新的 Session 对象**，并加入到 `Session 列表`。

但是，如果 `Session 列表` 中已经有 `session 创建请求` 对应的 `session id` 则：
- 视为现有 session 的重新连接请求(`session resume`)。 不需要创建 session 对象。

请注意，Session Acceptor 的实现可能是个外部线程或协程。可能在进程运行的任何时候提交 `session 创建请求`。

## 系统通知路由（2026-07）

Gateway 实现 `NoticeSink` Protocol（定义于 `session_events.py`），在 `__init__` 时注入 `MemoryWriterAgent`。

`Gateway.notify()` 接收后台 Agent 的通知，通过 `session_id` 查找对应 Session，
调用 `session.post_event(SystemNotice(...))` 将通知入队。session 不存在时丢弃并日志警告，
与 daemon "可接受丢失"语义一致。

参见：
- [session.md — 事件队列与跨线程事件推送](/docs/impl-spec/session.md)
- [memory-writer-agent-spec.md — 写入确认通知](/docs/impl-spec/memory-writer-agent-spec.md)

## Session 退出清理（2026-07）

Session 退出时（如 channel 断开触发 `QuitEvent`），Gateway 自动从 `Session 列表` 中移除该 session。

实现方式：`Gateway.accept_session()` 给 `session.run()` 的 task 加 `add_done_callback`，
回调中调用 `_cleanup_session(session_id)` 从 `self.sessions` 中 `pop`。

参见：
- [web-session-acceptor.md — Session 超时回收](/docs/impl-spec/web-session-acceptor.md)
- [session.md — QuitEvent 与退出流程](/docs/impl-spec/session.md)

## 结构
```
Gateway --> Session Acceptor
        |-> Session list -> session
        |-> NoticeSink (注入 MemoryWriterAgent)

Session --> Channel
        |-> Agent
```


## 进程入口

进程入口 `/src/everlingo/gateway/gateway.py` 。 进程提供命令行参数：
```bash
# 启动 Stdio Session Acceptor
gateway --channel_stdio

# 默认启动 Stdio Channel
gateway

# 启动 Wechat Session Acceptor。
gateway --channel_wechat

gateway --channel_web
```

启动时，检查用户个性初始化的`必选设置`:
- 界面语言
- 目标学习语言
如果未设置，设置为以下默认值：
- 界面语言 = zh-CN
- 目标学习语言 = en

## Session Acceptor

见 [Session Acceptor](/docs/impl-spec/session-acceptor.md)




