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
https://github.com/corespeed-io/wechatbot/raw/refs/heads/main/python/README.md
https://pypi.org/project/weixin-bot-sdk/
https://www.wechatbot.dev/zh/python -->