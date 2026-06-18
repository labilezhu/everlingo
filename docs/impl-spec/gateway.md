# Gateway 服务

一个独立的 python 进程。负责：
- 管理一个 [Channel](/docs/impl-spec/channel.md) 实例，负责 Channel 的全生命周期：初始化、启动。
- 为 Channel 实例，建立专用的 Agent 实例。并把这种 Channel 实例 与 Agent 实例的绑定，封装为一个 Session 对象。每个 Session 对象有自己的线程，loop 阻塞读取 channel 的消息。
- 


进程入口 `/src/everlingo/gateway/gateway.py` 。 进程提供命令行参数：
```bash
# 启动 Stdio Channel
gateway --channel_stdio

# 默认启动 Stdio Channel
gateway

# 启动 Wechat Channel。 注意，暂时不实现
gateway --channel_wechat
```

## Session
主要代码示例： `/src/everlingo/gateway/session.py`

