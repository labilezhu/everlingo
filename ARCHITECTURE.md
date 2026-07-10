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


## 核心设计
- [Workspace](docs/impl-spec/worksplace/workspace.md)
- [Session](docs/impl-spec/session.md)
- [Channel](docs/impl-spec/channel.md)
- [Chat Agent 实现](docs/impl-spec/chat-agent-spec.md)
- [Gateway 服务](docs/impl-spec/gateway.md)


### Workspace
![Workspace](docs/impl-spec/workspace.drawio.svg)

### Architecture
![Architecture](docs/impl-spec/arch.drawio.svg)

### Search
![Search](docs/impl-spec/search/search.drawio.svg)

## 配置

- [配置](docs/impl-spec/configuration.md)


## 应用的主入口
应用的主入口。指进程启动的入口点。参见： [app-entry.md](/docs/impl-spec/app-entry.md)

