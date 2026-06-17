from wechatbot import WeChatBot

bot = WeChatBot()

@bot.on_message
async def handle(msg):
    print(f"[{msg.type}] {msg.user_id}: {msg.text}")
    await bot.reply(msg, f"Echo: {msg.text}")
    await bot.reply(msg, f"Echo2: {msg.text}")
    await bot.reply(msg, f"**B** B *B* ")
    await bot.send( msg.user_id, "SEND" )

bot.run()  # 扫码登录 + 开始监听