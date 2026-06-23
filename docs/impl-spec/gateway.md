# Gateway

一个独立的 python 进程。

负责：
- 按启动参数要求，创建相应的 `Session Acceptor` 。
- 维护和管理一个 `Session 列表`。Session 用 session id 标识
- 接收和处理来自 `Session Acceptor` 的 `session 创建请求`。
  
## `session 创建请求` 的处理
为 Channel 实例，建立专用的 Agent 实例。并把这种 Channel 实例 与 Agent 实例的绑定，封装为一个 Session 对象。

Gateway 收到 `session 创建请求` 时，一般需要**创建新的 Session 对象**，并加入到 `Session 列表`。

但是，如果 `Session 列表` 中已经有 `session 创建请求` 对应的 `session id` 则：
- 视为现有 session 的重新连接请求(`session resume`)。 不需要创建 session 对象。

请注意，Session Acceptor 的实现可能是个外部线程或协程。可能在进程运行的任何时候提交 `session 创建请求`。



## 结构
```
Gateway --> Session Acceptor
        |-> Session list -> session

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




