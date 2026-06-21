# Session Acceptor

负责：
- 接受 Session 创建请求，创建相应的 `Channel` ，然后向 [Gateway](/docs/impl-spec/gateway.md) 提交 `session 创建请求` 。
- 不负责创建 Session 对象

`session 创建请求` 包括以下元素：
- `Channel`
- `session id`: Session Acceptor 生成。用 uuid string

## Session Acceptor 实现

## Stdio Session Acceptor
启动时立即创建一个 Stdio Session。 包括一个 Stdio Channel。不支持 `session resume`。

## Wechat Session Acceptor
启动时立即创建一个 Wechat Session。 包括一个 Wechat Channel。不支持 `session resume`。

## Session
见 [Session](/docs/impl-spec/session.md)

## Channel
参考 [channel.md](/docs/impl-spec/channel.md)


