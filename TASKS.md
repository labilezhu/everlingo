# Current Sprint

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"
 - 2026-06-23 10:00 | Channel Protocol: 新增 ChannelMetadata dataclass、send_sound 和 get_metadata 方法，以及对应测试
 - 2026-06-23 22:00 | 语音发送功能：新增 tts 模块（EdgeTTSProvider）、voice_speak 工具、Channel 改 ABC、Session 构造 MainAgent、分级语音 prompt 注入、动态 tool list、更新测试与文档
 - 2026-06-24 15:00 | 多消息回复：MainAgent.invoke 返回 list[MessageEvent]，每个非空 AIMessage.content 作为独立回复；Session 逐条 channel.send 形成多气泡；ToolMessage 不计入回复但保留在历史；更新测试与 agents-spec.md / session.md
 - 2026-06-24 16:00 | 文档同步：按 README.md 重写 PRODUCT.md，明确区分"已经能做什么"和"正在路上"；补齐已实现的多端接入（微信/Web/TUI）与多语言支持描述；去除技术细节与图片
 - 2026-06-24 17:30 | Web 通道支持语音朗读：WebChannel.get_metadata 声明 mp3 支持（自动挂载 voice_speak 工具与分级 prompt），send_sound 广播 sound SSE 事件（base64 mp3），前端独立语音气泡含重听按钮（缓存 blob URL，无需后端再合成）；更新 tests/test_web_channel.py 与 docs/impl-spec/web-session-acceptor.md
 - 2026-06-24 18:00 | 修复 tests/test_web_acceptor.py 5 个失败用例：旧的 `_make_gateway` 用已废弃的 `Session(channel, agent=...)` 签名构造实例；改为用 MagicMock 模拟 session（测试只关心 web_acceptor 行为，不依赖 Session 内部实现）






