# Channel

Channel 是 Agent 运行时对外收发消息的抽象接口。它的 python 定义如： `/src/everlingo/gateway/channels/channel.py`

其它具体的 Channel 实现这个抽象的接口。

## 内置的 Channel 实现

- [Stdio Channel](/docs/impl-spec/channel-stdio.md)