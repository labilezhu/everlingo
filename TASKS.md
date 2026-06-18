# Current Sprint

## 计划中的任务

## 可执行的任务

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"
 - 2026-06-18 | 编写 Wechat(微信) 消息 Channel。实现 `src/everlingo/gateway/channels/wechat_channel.py`（WechatChannel 类，使用 wechatbot-sdk，queue.Queue 线程安全消息队列）；更新 `gateway.py` 接入 WechatChannel，新增 `_run_wechat()` 函数；新增测试 `tests/test_wechat_channel.py`（8 个 Mock 测试，全部通过）。
 - 2026-06-18 | 使用 MIT 许可证。创建 `LICENSE` 文件，更新 `pyproject.toml` 添加 `license = "MIT"`
 - 2026-06-18 | 支持 `日本语(ja)` 作为 目标学习语言(target_language) 或 界面语言(interface_language)。更新 `models.py` LANGUAGES dict 和字段注释；更新 `agent.py` 重构 _lang_display_name() 引用 LANGUAGES 并更新 system prompt；更新 `everlingo.example.yaml` 和 `DOMAIN.md` 文档；添加日语相关测试用例。

