
我准备为项目加入知识点记忆功能。直接让 LLM Agent 读写 memory markdown 文件。设计文档见 docs/impl-spec/chat-agent-spec.md 中的 “### memory writer agent 同步筛选” 一节 与 docs/impl-spec/memory-writer-agent-spec.md。 

实现分几个阶段，现在阶段主要是内部测试用，看实现可行性：
- 先不使用全文搜索和语义搜索。
- 用户知识知识可能会被记忆，但不直接或间接访问记忆的内容
- 记忆只写不读，不搜索

请你就这个设计，在产品层面，以及实现设计层面，说说你的意见。


---



我准备为项目加入知识点记忆功能。现开发一个可行性测试版本，我将自己运行试用，通过观察日志，作一个可行性测试。
- 先实现记忆筛选[Memory Extract Agent](docs/impl-spec/memory-extract-agent-spec.md)功能。
- 暂不实现 [Memory Writer Agent](docs/impl-spec/memory-writer-agent-spec.md)

你计划一下。


