# 设计说明 - phase 0.1

## 技术选型

作为一个开源项目。

### 编码技术栈

- 后端基于 LLM 和 langchain python 开发

### LLM Provider

实现时，应该兼容 [Open AI Chat Completions endpoint](https://developers.openai.com/api/reference/chat-completions/overview)。直接使用 langchain 实现这个兼容。
测试时用 OpenRouter 的 Open AI Chat Completions endpoint base url: `https://openrouter.ai/api/v1` 。 api key 由环境变量注入。


## 实现设计

LLM tools:

### 管理用户个性初始化

tool name: user_profile

#### tool description
管理用户个性初始化

`必须设置项`：
- 界面语言
- 目标学习语言。约束规则：不能和 对话语言 相同

##### functions

###### 保存设置
tool name: user_profile
parameters: 
    entitys : list[(key, value)]  , 如 []


