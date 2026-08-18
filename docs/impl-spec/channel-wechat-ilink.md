# Wechat(微信) 消息 Channel

实现 Wechat 消息收发的 Channel 。 使用 wechatbot-sdk 。

实现主文件： `src/everlingo/gateway/channels/wechat_channel.py`。

## wechatbot-sdk

wechatbot-sdk 是一个 python 连接 wechat 聊天的 SDK。 通过它，程序可以连接上手机 wechat ，接收和发送 markdown 格式的文本消息。

安装方法：
```bash
pip install wechatbot-sdk
```

### 使用
```python
from wechatbot import WeChatBot

bot = WeChatBot()

@bot.on_message
async def handle(msg):
    print(f"[{msg.type}] {msg.user_id}: {msg.text}")

    # 被动回复消息
    await bot.reply(msg, f"Echo: {msg.text}")
    # 发出的消息支持 markdown 格式
    await bot.reply(msg, f"**B** B *B* ")
    # 主动发送消息
    await bot.send( msg.user_id, "SEND" )
    # 主动发送音频消息
    data = open("/home/labile/u.wav", "rb").read()
    await bot.send_media( msg.user_id, {"file": data, "file_name": "report.wav"} )

# 在 stdout 中输出 登录QR-CODE，提示用户在浏览器打链接，并扫码登录。用户完成登录后，开始监听，block 当前线程。 所以必要时需要专用线程。
bot.run()
```

注意事项：
- WeChatBot 对象是个长生命的单例对象。应用运行生命周期内只创建一次。
- 主动发送消息必须带上之前消息的 user_id 。 所以 user_id 应该在每收到消息时保存在应用全局内存中
- 由于  wechatbot-sdk 的运行需要连接网络和 wechat 服务，并且需要手工 login 。单元测试时，只能 Mock 或不作单元测试。

### 接收图片

```python
@bot.on_message
async def handle(msg):
    # download a raw CDN reference directly
    if msg.images:
        for img in msg.images:
            print(f"  图片: {img.url}")
            raw = await bot.download_raw(img.media, img.aes_key)
```

### Wechat Channel 图片落地（实现说明）

ref: [docs/ADR/20260818-image-chat-wechat.md](/docs/ADR/20260818-image-chat-wechat.md)

- `bot.download_raw(img.media, img.aes_key)` 取原始字节（`img.aes_key` 为 `None` 时回落 `media.aes_key`）；
  下载在 bot 线程回调完成，原始字节随 `_WechatIncoming.image_bytes` 入队。
- 服务端（Session loop）用 `sniff_image_mime` 嗅探 MIME（jpeg/png/webp），非支持格式按失败处理。
- `src_resource_sha256 = sha256_of_bytes(下载字节)`；调 `image_store.save(session_id, sha, data, mime)`
  复用与 Web 上传同一的落盘 / 预处理 / ImageAsset 注册逻辑。
- 构造带 `chat.attachments` 的 `UserInputEnvelope`；`recv_envelope` 内在 Session loop 调度 `eager_warm`。
- 多图只下载/取第一张；下载失败/格式不支持：有文字则丢图留字，纯图则回友好提示不生成空 turn。
- `ChannelMetadata.supported_image=True` 时 Agent 自动注入 `analyze_image` 与 `copy_session_image_to_vault`。

### 分开 login 与 message long-polling

`bot.run()` 的过程，其实包括了：

```python
await bot.login(force=False)	# QR login (auto-skips and return success if credentials exist)
await bot.start()	# Start long-poll loop
```

有需要分阶段，明确scan QR code 结果时，可以分开调用。


### sdk 保存用户 credentials

用户登录认证后， credentials 保存于。由 SDK 自己处理的。应用层不需要关注：

`~/.wechatbot/credentials.json`
```json
{
  "token": "1111@im.bot:22222",
  "baseUrl": "https://ilinkai.weixin.qq.com",
  "accountId": "33333@im.bot",
  "userId": "4444-5555@im.wechat",
  "savedAt": "2026-06-17T12:00:58.409100+00:00"
}
```

### 指定 sdk 保存用户 credentials 的文件

Wechat 的证书文件，需要保存在 [workspace](/docs/impl-spec/worksplace/workspace.md) 的子目录下。具体目录和文件是： "$workspace/plugins/channels/wechat_channel/credentials/credentials.json" 。
如果目录不存在，需要在调用 `WeChatBot()` 前自动创建。

WeChatBot()调用示例：
```python
bot = WeChatBot(
    base_url="https://ilinkai.weixin.qq.com",   # default
    cred_path="$workspace/plugins/channels/wechat_channel/credentials/credentials.json",   # default
    on_qr_url=lambda url: print(f"Scan: {url}"),
    on_scanned=lambda: print("Scanned!"),
    on_expired=lambda: print("Expired..."),
    on_error=lambda err: print(f"Error: {err}"),
)
```


<!-- ### 测试 SDK 的代码
/src/everlingo/wechat.py 是测试这个 SDK 的代码。

```bash
uv run python -m everlingo.wechat
```


### SDK 参考文档
https://github.com/corespeed-io/wechatbot/blob/main/python/README.md
https://github.com/corespeed-io/wechatbot/raw/refs/heads/main/python/README.md
https://raw.githubusercontent.com/corespeed-io/wechatbot/refs/heads/main/python/README.md
https://pypi.org/project/weixin-bot-sdk/
https://www.wechatbot.dev/zh/python -->

## in-process 托管与自动启动（2026-07 设计变更）

Wechat channel 不再作为独立子进程运行，改由 web 进程内的 `WechatRuntime`（`src/everlingo/gateway/wechat_admin/runtime.py`）in-process 托管。详见 [workspace-console/ws-console-arch.md](/docs/impl-spec/workspace-console/ws-console-arch.md)。

### 托管方式

- `WechatRuntime` 实现 `SessionAcceptor` 协议，由 `Gateway.run` 按 config-driven（无参）或 explicit flag（`--channel_wechat` / `--channel_web`）创建。
- runtime 持有 `WechatChannel` 实例 + 跨进程单例锁（`acquire_lock`，flock on `$workspace/plugins/channels/wechat_channel/gateway.lock`，防止 standalone 与 web 内嵌同时跑）。
- web console router 直调 runtime 的 `start_wechat()` / `stop_wechat()` / `status()`（同进程内存调用，不经 IPC）。

### on_logined 持久化 enable

用户首次经 web console 登录成功（state→logined）后，runtime 的 `on_logined` 回调向 `everlingo.yaml` 写入 `plugins.channels.channel_wechat.enable: true`（节点不存在则补写）。用户主动停止则写 `enable: false`。

### 重启后自动恢复

gateway 无参启动时读 `channel_wechat.enable`，为 `true` 则自动 `WechatRuntime(auto_start=True)` 启动 wechat。因 `credentials.json` 已存（首次登录时 SDK 保存于 `$workspace/plugins/channels/wechat_channel/credentials/credentials.json`），`bot.login(force=False)` 自动跳过 QR 直接 logined（见上 §分开 login 与 message long-polling），用户无感知恢复。credential 过期时回到 `waiting_scan`，用户扫码后 `on_logined` 再次确认 enable。

### standalone 入口

`python -m everlingo.gateway --channel_wechat` 仍可用（无 web 环境）：`WechatRuntime(auto_start=True)` 单独跑，SIGINT/SIGTERM 经 `loop.add_signal_handler` 触发 `stop_wechat()` 优雅停。此时锁被占用，web console 的 `start_wechat` 会进入 `conflict` 态。