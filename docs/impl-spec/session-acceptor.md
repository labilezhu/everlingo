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

## Web Session Acceptor
参考 [Web Session Acceptor](/docs/impl-spec/web-session-acceptor.md)

## Session
见 [Session](/docs/impl-spec/session.md)

## Channel
参考 [channel.md](/docs/impl-spec/channel.md)



## Wechat Channel 自动恢复（可选）

首次部署的 `everlingo.yaml` 仅配置 `channel_web`，不含 `channel_wechat`。要启用微信通道：

1. 浏览器打开 web console（header `Me` → Workspace Console → wechat channel admin），点「启动」，扫码登录微信。
2. 登录成功后，系统自动向 `everlingo.yaml` 写入 `plugins.channels.channel_wechat.enable: true`，并保存微信 credentials 到 `$workspace/plugins/channels/wechat_channel/credentials/credentials.json`。
3. 此后每次容器/进程重启，gateway 无参启动会读 `channel_wechat.enable` 自动恢复 wechat，因 credentials 已存，`login(force=False)` 免扫码直接登录，无需手动干预。

用户在 console 点「停止」会写 `enable: false`，下次重启不再自动启。再次「启动」并登录成功后恢复 `enable: true`。

详见 [workspace-console/ws-console-arch.md](/docs/impl-spec/workspace-console/ws-console-arch.md)。
