# Current Sprint

## 完成的任务

- 2026-06-17 23:58 | logging.py → log_utils.py（避免 shadow stdlib logging 导致 ImportError）；更新 main.py/llm.py/test_logging.py 的 import；launch.json wechat 配置改用 module 模式
- 2026-06-17 23:55 | 文件重命名：profile.py → setting.py（内容已不限于 UserProfile），同步更新所有 import 引用，PROFILE_PATH → SETTING_PATH，test_profile.py → test_setting.py
- 2026-06-17 23:50 | UserProfile 结构对齐 everlingo.example.yaml：新增 UserLanguage/UserBackground 子模型，interface_language/target_language 移入 language 下，hobbies/residence/gender 移入 background 下；更新 setting.py（简化为 model_validate/model_dump）、chat.py、test_setting.py、test_unified_agent.py
- 2026-06-17 23:30 | 配置实现由 dataclass 重构成 pydantic
- 2026-06-17 23:00 | 实现 LLM tool 调用日志：添加 log_tool_call 装饰器并应用到所有 tool 函数，日志格式为 tool_name + parameters + return，debug 级别
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


- 修改为基于 langchain agent 的 LLM 交互 (`from langchain.agents import create_agent`):
  - 新建 `tools.py`：实现 configuration_manager tool（get_schema/get_config/set_config）
  - 修改 `llm.py`：添加 create_agent() 工厂函数，包装 langchain.agents.create_agent
  - 修改 `dict_teacher.py`：接受 agent 替代 ChatOpenAI，使用 agent.invoke({"messages": [...]})
  - 修改 `trans_teacher.py`：同上模式
  - 修改 `chat.py`：为每位老师创建独立的 agent，system_prompt 在创建时注入
  - 更新对应测试：mock agent 返回 {"messages": [AIMessage(...)]}

- 建立一个 langchain python 开发环境的 code base
- 项目结构: `pyproject.toml`, `src/everlingo/`, `tests/`
- Domain models: `UserProfile`, `WordQuery`, `TranslationRecord`
- LLM 集成: LangChain + ChatOpenAI (兼容 OpenAI Chat Completions endpoint)
- 用户个性初始化: 界面语言 + 目标学习语言 (英语/简体中文)
- 意图分析: 规则驱动 (查单词 / 翻译)
- 词典老师: LLM 驱动的单词解释 (释义、词源、文化背景)
- 翻译老师: LLM 驱动的翻译 (含句式分析)
- TUI Chatbot: 终端 REPL 聊天循环
- 按照 impl-spec/configuration.md 生成 /.env.example 和 /everlingo.example.yaml
- 按照 impl-spec/configuration.md 修改配置代码:
  - config.py: 支持从 YAML sys_setting 读取配置，优先级高于环境变量
  - profile.py: 改用 YAML 格式，位置 `~/.everlingo/everlingo.yaml`，支持嵌套 user_profile 结构
  - models.py: UserProfile 增加 background 和 dictionary_definition_style 字段
  - pyproject.toml: 添加 pyyaml 依赖
- 配置文件结构修正: 顶层配置对象改为 `EverLingoSetting`，包含 `SysSetting` 和 `UserProfile`
  - models.py: 新增 `SysSetting`、`EverLingoSetting` 类
  - profile.py: 新增 `load_setting()`/`save_setting()`，以 `EverLingoSetting` 为顶层对象
  - config.py: 改用 `load_setting().sys_setting` 获取系统配置
