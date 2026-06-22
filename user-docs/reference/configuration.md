# 配置参考

## Environment Variables
以下列出使用的环境变量。应用通过 [python-dotenv](https://github.com/theskumar/python-dotenv) 加载 `.env` 文件，
也可以通过 shell 环境变量直接注入。

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OPENAI_API_KEY` |  | LLM Provider API Key（必需） |
| `OPENAI_BASE_URL` |  | 兼容 OpenAI Chat Completions 的 API Base URL |
| `OPENAI_MODEL` |  | 使用的模型名称 |




## 配置文件 - EverLingoSetting
以下列出配置文件的信息。

配置文件位置： `~/.everlingo/everlingo.yaml` 。 配置文件使用 yaml 格式。

**yaml 结构如下。必须按照这个结构去实现**
```yaml
sys_setting:
  openai_api_key:
  openai_base_url: 
  openai_model: 
  logging_setting:
  tracing_setting:
user_profile:
```

配置文件包括以下子小节的内容。

在代码中， class 名称叫 `EverLingoSetting`. 


### 系统设定 - SysSetting

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `openai_api_key` |  | LLM Provider API Key（必需） |
| `openai_base_url` |  | 兼容 OpenAI Chat Completions 的 API Base URL |
| `openai_model` |  | 使用的模型名称 |

配置文件的配置项目的优先级高于 Environment Variables 。 即如果一个语义相同的配置项，在配置文件和 Environment Variables 中均配置了，优先使用 配置文件的配置项 。

在代码中， class 名称叫 `SysSetting`.

#### 日志设定 - LoggingSetting

| 变量        | 默认值                          | 说明                                                  |
| ----------- | ------------------------------- | ----------------------------------------------------- |
| `log_file`  | ~/.everlingo/logs/everlingo.log | 日志文件路径                                          |
| `log_level` | debug                           | 日志文件中的日志输出级别。可选：debug/info/warn/error |



#### 跟踪设定 - Tracing

| 变量                  | 默认值 | 说明                                              |
| --------------------- | ------ | ------------------------------------------------- |
| `tracing_service`     |        | 可选： langfuse  。空值时不启动任何 tracing       |
| `langfuse_secret_key` |        | langfuse secret key。如 sk-lf-xxxx                |
| `langfuse_public_key` |        | langfuse public key。如 pk-lf-ce-xxxx             |
| `langfuse_base_url`   |        | langfuse base url 。如 http://192.168.16.130:3300 |



### 用户 Profile - UserProfile

首次运行时交互生成，之后自动加载。

配置项参考 [DOMAIN.md](/DOMAIN.md) 中 `用户 Profile` 一节。

在代码中， class 名称叫 `UserProfile`. 

### 用户自由偏好笔记 - USER.md

存放位置： `~/.everlingo/USER.md` ，Markdown 自由文本。

参考 [DOMAIN.md](/DOMAIN.md) 中 `用户自由偏好笔记 - USER.md` 一节。

可通过与 Agent 聊天让 Agent 调用 `user_doc` 工具更新，也可用外部编辑器直接编辑。
