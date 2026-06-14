# Active Phase

Phase 1 - DEMO

相关文档见： [ROADMAP.md](ROADMAP.md) 中的 [Phase 1 - DEMO] 一节

# Current Sprint

- [x] 建立一个 langchain python 开发环境的 code base

## 完成内容

- 项目结构: `pyproject.toml`, `src/everlingo/`, `tests/`
- Domain models: `UserProfile`, `WordQuery`, `TranslationRecord`
- LLM 集成: LangChain + ChatOpenAI (兼容 OpenAI Chat Completions endpoint)
- 用户个性初始化: 界面语言 + 目标学习语言 (英语/简体中文)
- 意图分析: 规则驱动 (查单词 / 翻译)
- 词典老师: LLM 驱动的单词解释 (释义、词源、文化背景)
- 翻译老师: LLM 驱动的翻译 (含句式分析)
- TUI Chatbot: 终端 REPL 聊天循环
- 测试: 18 个测试全部通过
