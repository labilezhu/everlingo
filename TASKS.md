# Current Sprint

## 计划中的任务

## 可执行的任务
- 配置实现的 由 dataclass 重构成 pydantic 。项目现在的配置管理实现是基于 python dataclass 的。需要重构成基于 pydantic 的。具体实现说明见 /docs/impl-spec/configuration.md 中的 “/docs/impl-spec/configuration.md”：
  - 需要有 field schema 定义
  - 需要 schema 校验
  - 可以生成 JSON Schema


## 完成的任务
- 2026-06-17 23:00 | 实现 LLM tool 调用日志：添加 log_tool_call 装饰器并应用到所有 tool 函数，日志格式为 tool_name + parameters + return，debug 级别
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"
- 2026-06-16 19:45 | 修复 Langfuse 4.x 兼容性：CallbackHandler 不再接受凭证参数，改为先初始化 langfuse.Langfuse(secret_key/public_key/host) 配置 OTEL exporter，再创建无参 CallbackHandler()
- 2026-06-16 19:30 | 配置文件结构修正：logging_setting/tracing_setting 移入 sys_setting 下，修正 models.py、profile.py、everlingo.example.yaml、tracing.py、logging.py 及相关测试文件
- 2026-06-16 18:00 | 添加 __main__.py 使 python -m everlingo 可用，支持 VSCode debug 的模块模式
- 2026-06-16 18:00 | 创建 .vscode/launch.json debug 配置（module 模式 + PYTHONPATH）
- 2026-06-16 15:20 | 实现 Tracing 配置：TracingSetting dataclass 及序列化/反序列化、更新 everlingo.example.yaml 示例配置
- 2026-06-16 15:20 | 实现 Langfuse 跟踪 LLM 流量：setup_tracing() 集成 Langfuse CallbackHandler 到 LLM
- 2026-06-16 10:30 | 实现多轮会话支持：chat.py 累积 messages 历史，agent.invoke 传入完整历史上下文而非单条消息
- 2026-06-16 10:30 | 实现 Observability 日志系统：LLM 请求/响应写入 ~/.everlingo/logs/everlingo.log，日志级别 debug
- 2026-06-16 10:30 | 实现 LoggingSetting 配置项：log_file / log_level 可配置，集成到 EverLingoSetting 序列化
- 2026-06-15 17:33 | 重构为统一 Agent 架构：移除 IntentAnalyzer，使用单一 LangChain Agent 处理所有意图（查词、翻译、配置管理）
- 2026-06-15 10:30 | 重构 tools 为多 toolset 架构
