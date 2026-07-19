# Channel

Channel 是 Agent 运行时对外收发消息的抽象接口。它的 python 定义如： `/src/everlingo/gateway/channels/channel.py`
其它具体的 Channel 实现这个抽象的接口。

### 消息接收：envelope 协议（2026-07）

所有 Channel 子类通过 `recv_envelope() -> UserInputEnvelope | None` 产出结构化用户输入，取代原有 `recv() -> str | None`。

`UserInputEnvelope` 是统一结构化用户输入协议（详见 [envelope-spec.md](envelope-spec.md)），能够携带选词、上下文、来源、设备、任务偏好等结构化信息。stdio/wechat/web 等所有内置 Channel 均统一产 envelope。


## 内置的 Channel 实现

- [Stdio Channel](/docs/impl-spec/channel-stdio.md)
- [Wechat(微信) 消息 Channel](/docs/impl-spec/channel-wechat-ilink.md)
- Web Channel