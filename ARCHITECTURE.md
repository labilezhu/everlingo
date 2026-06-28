# 架构设计

暂时是一个单体 python 程序的架构。

## 技术选型

作为一个开源项目。

### 编码技术栈

- 后端基于 LLM 和 langchain python 开发
- 使用 python venv 作为环境

### LLM Provider

实现时，应该兼容 [Open AI Chat Completions endpoint](https://developers.openai.com/api/reference/chat-completions/overview)。直接使用 langchain 实现这个兼容。
测试时用 OpenRouter 的 Open AI Chat Completions endpoint base url: `https://openrouter.ai/api/v1` 。 api key 由环境变量注入。


## 配置

- [配置](/docs/impl-spec/configuration.md)


## 实现设计
- [Agent 实现](/docs/impl-spec/chat-agent-spec.md)
- [Gateway 服务](/docs/impl-spec/gateway.md)

## Agents 数据流水线

```
Chat Agent  →  Memory Extract Agent  →  Memory Writer Agent
(对话回复)     (筛选 + 结构化抽取)       (异步写 vault)
```

- Chat Agent 在返回用户回复后，把本轮对话 delta 交给 Memory Extract Agent。
- Memory Extract Agent 筛选并结构化为 entries，转交给 Memory Writer Agent。
- Memory Writer Agent 异步写入 memory vault。

## 应用的主入口
应用的主入口。指进程启动的入口点。参见： [app-entry.md](/docs/impl-spec/app-entry.md)

