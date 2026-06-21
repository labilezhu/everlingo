# Session

负责：
- 管理一个 [Channel](/docs/impl-spec/channel.md) 实例，负责 Channel 的全生命周期：初始化、启动。
- 为 Channel 实例，建立专用的 Agent 实例。并把这种 Channel 实例 与 Agent 实例的绑定，封装为一个 Session 对象。每个 Session 对象有自己的协程，loop 阻塞读取 channel 的消息。


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