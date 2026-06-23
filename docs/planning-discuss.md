这个产品计划实现一个持久保存（记忆）用户查过的语言知识点（包括单词、短语、语法），并为 Agent 回答用户问题时，提供记忆功能，以针对之前的查询历史提供更有价值的帮助。
其实就是一个 wiki 类型的知识库，但内容是根据用户查询来动态生成的。用户也可以通过 Agent 对话修改生成的内容，可加入知识点备注。
在用户与 Agent 交互时，Agent 可以在需要时查询这个 wiki 以了解用户之前查询过的情况。
如：
场景1：
用户输入: ambitious
Agent 回复： 这个词你上次 2020 年 11 月时查询过了，这是第 2 次查询。当时的场景和知识点回顾如下： ……

场景2：
用户输入: I would rather eat apple.
Agent 回复： would rather 这个短语，你上次 2020 年 11 月时查询过了，这是第 6 次查询。。当时的场景和知识点回顾如下： ……


请你对这个产品的功能设计有什么建议吗？不是技术方案，只说产品设计。


---

计划为这个产品写一个产品介绍和实现现状说明的推广文章，发微信公众号
现在已经实现了：
- 通过 Chatbot 对话的个性化语言知识问答
- 动态学习记忆用户个性化要求
- 多端接入
  - 支持手机微信 ClawBot 扫码接入聊天
  - 支持网页和终端接入
  - 支持 英语、日本語、法语、德语 。

文章需要有产品的特性介绍，包括已经实现和未实现的。要写得接地气，但也要比较实在，不能太浮夸。

文章大概 2000 字内。

开源项目地址：https://github.com/labilezhu/everlingo


---

如果我要实现 wechat channel 下，在识别用户消息的意图是查单词或翻译时，调用 https://OPENAI_BASE_URL/audio/speech 合成 TTS 。音频消息发到微信。发送方法参考 docs/impl-spec/channel-wechat-ilink.md

---

讨论一下这个方案的设计，你可以提出不同建议。
- 增加功能： chatbot 可以在用户的要求下，自动选择性发送语音给用户。
  - 发送语音的选择逻辑： 由 llm 判断： 
    - 只在用户在个 `个性化偏好设置` 或 对话中显式要求发送语音时，才发送语音。
  - 语音的内容：由 llm 判断： 
    - 语音的内容：要查的单词发音、要翻译的句子、「单词发音」和「短句示范发音」，而「整段回复朗读」只在用户显式要求时才做。
  - 发送语音需要满足以下条件：
    - channel 的 get_metadata() 返回的 supported_sound_media_format 包含 "mp3"
  - 用户在对话中明确要求发送语音，但 channel 不支持时，LLM 应该用文字告知「当前通道不支持语音」
  
  实现细节： Agent 只有在 channel 的 metadata->supported_sound_media_format 支持 "mp3"，才注入语音相关的 prompt 内容。

  架构：
    新增：
    - channel 的 metadata->prompt 文本注入到 agent.py 的 system prompt 中。为 agent 提供对 channel 特性、限制、支持语音情况有了解
    - 声音的生成(TTS)。 当前使用 Edge TTS，但需要抽象设计，以后可能使用 openai / openrouter 的 api 。
    - 发送声音给用户：现有的 Channel 已经有 send_sound() 方法。
    - 声音的生成(TTS)和发送，合并在一个 llm tool。叫 `voice_speak` 中。
      - 声音的生成(TTS)和发送，涉及网络 IO , 应该是异步的，不要让 llm 等待结果。必要时启动新协程或线程。
      - 只有在 channel 的 metadata->supported_sound_media_format 支持 "mp3" 时，提供给 Agent 作为可选工具。 语音的生成(TTS) 以及 channel 发送失败不影响主流程(即 llm tool 不返回失败)，但需要 error 日志记录有及 stderr 输出。
    
    调整：
    - 每个 Session 在初始化时，构造自己的 MainAgent 和 动态的 tool list，而不是在 gateway.py 构造 MainAgent。

