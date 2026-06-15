# 配置参考

## Environment Variables
以下列出使用的环境变量。应用通过 [python-dotenv](https://github.com/theskumar/python-dotenv) 加载 `.env` 文件，
也可以通过 shell 环境变量直接注入。

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OPENAI_API_KEY` | 无默认 | LLM Provider API Key（必需） |
| `OPENAI_BASE_URL` | 无默认 | 兼容 OpenAI Chat Completions 的 API Base URL |
| `OPENAI_MODEL` | 无默认 | 使用的模型名称 |




## 配置文件
以下列出配置文件的信息。

配置文件位置： `~/.everlingo/everlingo.yaml` 。 配置文件使用 yaml 格式。

配置文件包括以下子小节的内容。 yaml 结构示例如下 :
```yaml
sys_setting:
  openai_api_key:
  openai_base_url: 
  openai_model: 
user_profile:
```

### 系统设定 - sys_setting

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `openai_api_key` | 无默认 | LLM Provider API Key（必需） |
| `openai_base_url` | 无默认 | 兼容 OpenAI Chat Completions 的 API Base URL |
| `openai_model` | 无默认 | 使用的模型名称 |

配置文件的配置项目的优先级高于 Environment Variables 。 即如果一个语义相同的配置项，在配置文件和 Environment Variables 中均配置了，优先使用 配置文件的配置项 。

### 用户 Profile - user_profile

首次运行时交互生成，之后自动加载。

配置项参考 [DOMAIN.md](/DOMAIN.md) 中 `用户 Profile` 一节。
