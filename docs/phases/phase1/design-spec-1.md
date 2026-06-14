# 技术规范 - phase 1

## 技术选型

作为一个开源项目。

### 编码技术栈

- 后端基于 LLM 和 langchain python 开发

### LLM Provider

实现时，应该兼容 [Open AI Chat Completions endpoint](https://developers.openai.com/api/reference/chat-completions/overview)。直接使用 langchain 实现这个兼容。
测试时用 OpenRouter 的 Open AI Chat Completions endpoint base url: `https://openrouter.ai/api/v1` 。 api key 由环境变量注入。


### Domain model
[domain-model-1.md](domain-model-1.md)

## 实现设计

- [LLM tools](tools-1.md)



