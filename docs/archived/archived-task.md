# Current Sprint

## 完成的任务

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
