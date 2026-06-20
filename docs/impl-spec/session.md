# Session

负责：
- 管理一个 [Channel](/docs/impl-spec/channel.md) 实例，负责 Channel 的全生命周期：初始化、启动。
- 为 Channel 实例，建立专用的 Agent 实例。并把这种 Channel 实例 与 Agent 实例的绑定，封装为一个 Session 对象。每个 Session 对象有自己的协程，loop 阻塞读取 channel 的消息。

主要代码示例： `/src/everlingo/gateway/session.py`

一个独立的 python 进程。负责：
- 管理一个 [Channel](/docs/impl-spec/channel.md) 实例，负责 Channel 的全生命周期：初始化、启动。
- 为 Channel 实例，建立专用的 Agent 实例。并把这种 Channel 实例 与 Agent 实例的绑定，封装为一个 Session 对象。每个 Session 对象有自己的协程，loop 阻塞读取 channel 的消息。


