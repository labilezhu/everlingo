# 配置参考

## Environment Variables
以下列出使用的环境变量。应用通过 [python-dotenv](https://github.com/theskumar/python-dotenv) 加载 `.env` 文件，
也可以通过 shell 环境变量直接注入。

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OPENAI_API_KEY` | — | LLM Provider API Key（必需） |
| `OPENAI_BASE_URL` | `https://openrouter.ai/api/v1` | 兼容 OpenAI Chat Completions 的 API Base URL |
| `OPENAI_MODEL` | `gpt-3.5-turbo` | 使用的模型名称 |


## 配置文件
以下列出配置文件的信息。

### 用户个性初始化

**配置文件位置：** `~/.everlingo/profile.json`

首次运行时交互生成，之后自动加载。

#### 配置项

| 字段 | 类型 | 可选值 | 说明 |
|------|------|--------|------|
| `interface_language` | string | `"zh-CN"`, `"en"` | 界面语言。不能与 `target_language` 相同 |
| `target_language` | string | `"zh-CN"`, `"en"` | 目标学习语言。不能与 `interface_language` 相同 |

#### 示例

```json
{
  "interface_language": "zh-CN",
  "target_language": "en"
}
```


#### 约束规则
- `interface_language` 和 `target_language` 均必须设置
- 两者不能相同


