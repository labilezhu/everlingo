# Current Sprint

## 计划中的任务

## 可执行的任务

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"
 - 2026-06-18 | 编写 Wechat(微信) 消息 Channel。实现 `src/everlingo/gateway/channels/wechat_channel.py`（WechatChannel 类，使用 wechatbot-sdk，queue.Queue 线程安全消息队列）；更新 `gateway.py` 接入 WechatChannel，新增 `_run_wechat()` 函数；新增测试 `tests/test_wechat_channel.py`（8 个 Mock 测试，全部通过）。
 - 2026-06-18 | 使用 MIT 许可证。创建 `LICENSE` 文件，更新 `pyproject.toml` 添加 `license = "MIT"`
 - 2026-06-18 | 支持 `日本语(ja)` 作为 目标学习语言(target_language) 或 界面语言(interface_language)。更新 `models.py` LANGUAGES dict 和字段注释；更新 `agent.py` 重构 _lang_display_name() 引用 LANGUAGES 并更新 system prompt；更新 `everlingo.example.yaml` 和 `DOMAIN.md` 文档；添加日语相关测试用例。
 - 2026-06-18 | Agent 按需重建 system prompt（配置版本驱动）。思路：`conf_manager.py` 维护模块级 `_config_version` 计数器，`set_config` 工具每次成功写入后递增；`MainAgent.__init__()` 记录当时的版本号，每次 `invoke()` 前调用 `_refresh_agent_if_needed()`，发现版本号变化时用 `load_profile()` 重新构建 system prompt 并 `create_agent()`，版本号同步后不再重建。新增测试：`test_tools.py`（计数器递增/不递增 3 项）、`test_unified_agent.py`（no-rebuild / rebuild-once / rebuild-on-each-change 3 项），共 13 个单元测试全部通过。
 - 2026-06-20 | `Channel.recv()` 改为 async。Protocol 签名 `def recv` → `async def recv`；`StdioChannel.recv` 用 `asyncio.to_thread` 包装 `input()`；`WechatChannel.recv` 用 `asyncio.to_thread` 包装 `queue.Queue.get()`；`Session.run()` 中 `channel.recv()` 调用加 `await`；相关测试适配（AsyncMock / asyncio.run 包装），无新增依赖。

