# Envelope 结构化用户输入格式

用户发出消息或 EverLingo 应用 UI 操作时，提供了结构化操作场景上下文（选词文本、上下文段落、来源 URL/文件、设备信息、用户期望任务）。其中很多信息可以作为知识点出现的场景，如知识点出现的相关文章标题和 url 等等。

## schema

用 `<envelope>JSON</envelope>` XML 包装，放入对方消息文本中。

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `schema_version` | int | 是 | 当前为 1。用于 schema 演进兼容 |
| `task` | enum | 是 | 用户偏好任务：`translate` / `look_up` / `none`。**是偏好不是命令**，LLM 可自由决定是否遵循 |
| `chat.message` | str | 否 | 用户自然语言输入。可能为空（用户仅点击了 UI 按钮，或仅上传了图片） |
| `chat.attachments` | array | 否 | 附件引用列表。**可为空数组**（纯聊天场景）。每项含 `src_resource_sha256`（用户端原始文件的 SHA256）与 `type`（如 `image`）。图片内容不进 envelope，Agent 经 `analyze_image(src_resource_sha256)` 工具取用理解结果（见图片学习能力 ADR） |
| `chat_context` | object | 否 | 用户操作时的上下文环境。默认 `{"resource_contexts": []}` |
| `chat_context.resource_contexts` | array | 否 | 上下文资源列表。**可为空数组**（纯聊天场景）。每项为 tagged union（见下方 `resource_context.kind`） |
| `source` | tagged union | 是 | 来源信息，用 `kind` 区分 |
| `device` | optional | 否 | 设备信息，用于个性化释义 |

> **附件与"延续话题"规则**：当 `chat.attachments` 非空时，即使 `chat.message` 为空，也表示用户提供了一段新的图片 Context 输入，**不触发** `task=look_up` 且 `chat.message` 为空且无 `selected_text` 时的"延续上一轮笔记话题"语义（该语义仅适用于纯文本空输入场景）。

### `task` 枚举

可选值：`translate` / `look_up` / `none`。

### `chat_context.resource_contexts`

数组元素以 `kind` 字段为 discriminator。当前定义 3 个 kind：

| kind | 使用场景 | 补充字段 |
|---|---|---|
| `vault_file` | Vault Editor 中打开的笔记文件 | `file_path` |
| `web_page` | 用户选词的 web 页面（与 `source` 信息有重叠，用于 LLM 理解上下文内容） | `url`, `title` |
| `selected_text` | 用户高亮选定的文本 | `text`, `start_line`, `start_column`, `paragraph_text` |

#### kind="vault_file"

```json
{
    "kind": "vault_file",
    "file_path": "items/vocab/embedding.md"
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file_path` | str | 是 | Vault 笔记条目文件路径 |

#### kind="web_page"

```json
{
    "kind": "web_page",
    "url": "https://example.com/article",
    "title": "Example Article"
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `url` | str | 是 | 页面 URL |
| `title` | str | 否 | 页面 title |

#### kind="selected_text"

```json
{
    "kind": "selected_text",
    "text": "structural",
    "start_line": 19,
    "start_column": 13,
    "paragraph_text": "The embedding of the steel rods in concrete ensures structural stability"
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `text` | str | 是 | 选定的文本内容 |
| `start_line` | int / null | 否 | 选定文本的开始行（辅助定位）。不可获取时为 null |
| `start_column` | int / null | 否 | 选定文本的开始列（辅助定位）。不可获取时为 null |
| `paragraph_text` | str / null | 否 | 选定文本所在的段落或上下文块（最多 500 字，超过时以 selected_text 为中心截取，保证包含选词）。不可获取时为 null |

### `source`

`source` 用 `kind` 字段作为 discriminator。当前定义 6 个 `kind`：

| kind | 使用场景 | 补充字段 |
|---|---|---|
| `plain` | stdio/wechat 请求 | 无额外字段 |
| `web` | Web Chatbot | `url`, `title`, `surface` |
| `chrome_ext` | Chrome Extension 网页选词 | `url`, `title`, `surface` |
| `pdf` | PDF 阅读器插件 | `file_path`, `page_number` |
| `epub` | EPUB 阅读器 | `book_id` |
| `ios_app` | iOS app 选词服务 | `bundle_id` |

#### kind="web"

```json
    "source": {
        "kind": "web",
        "url": "https://example.com/article",
        "title": "Example Article",
        "surface": "fullscreen"
    },
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `url` | str | 否 | 当前页面的 URL  |
| `title` | str | 否 | 当前页面的 title  |
| `surface` | enum | 否 | 界面类型。可选值：`fullscreen` (Standalone Web Chatbot)  |

#### kind="chrome_ext"

```json
    "source": {
        "kind": "chrome_ext",
        "url": "https://chatgpt.com/c/6a5e1033-22cc-83e8-aba3-d1daf5a1dde1",
        "title": "Chrome扩展侧边栏位置",
        "surface": "sidecar"
    },
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `url` | str | 否 | Chrome Extension 当前抓取选择内容的网页 URL  |
| `title` | str | 否 | Chrome Extension 当前抓取选择内容的网页 title  |
| `surface` | enum | 否 | 界面类型。可选：`sidecar` (Chrome扩展侧边栏位置) / `popup` (独立弹窗，未来)  |

#### kind="plain"

```json
    "source": {
        "kind": "plain",
    },
```

### device

示例：
```json
{
    "platform": "chrome_ext",
    "locale": "en-US",
    "timezone": "Asia/Hong_Kong"
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `platform` | enum | 否 | chrome_ext (Chrome Extension) / web (Web Chatbot)  |

## 场景示例

### 场景 1：Vault Editor 中嵌入的 Web Chatbot

```json
{
    "schema_version": 1,
    "task": "none",
    "role": "user",
    "chat": {
        "message": "user input text",
        "attachments": [
            {
            "src_resource_sha256": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1d0f",
            "type": "image",
            }
        ],        
    },
    "chat_context": {
        "resource_contexts": [
            {
                "kind": "vault_file",
                "file_path": "items/vocab/embedding.md"
            },
            {
                "kind": "selected_text",
                "text": "structural",
                "start_line": 19,
                "start_column": 13,
                "paragraph_text": "The embedding of the steel rods in concrete ensures structural stability"
            }
        ]
    },
    "source": {
        "kind": "web",
        "url": "https://mydomain.com:6457/editor?lang=en&path=items%2Fvocab%2Fembedding.md",
        "title": "🐹 小记笔记编辑器",
        "surface": "fullscreen"
    },
    "device": {
        "platform": "web",
        "locale": "en-US",
        "timezone": "Asia/Hong_Kong"
    }
}
```

### 场景 2：Chrome Extension Chatbot

```json
{
    "schema_version": 1,
    "task": "translate",
    "chat": {
        "message": ""
    },
    "chat_context": {
        "resource_contexts": [
            {
                "kind": "selected_text",
                "text": "structural",
                "paragraph_text": "The embedding of the steel rods in concrete ensures structural stability"
            }
        ]
    },
    "source": {
        "kind": "chrome_ext",
        "url": "https://blog.mygraphql.com/en/posts/ai/ai-personal-assistant/openclaw-concepts/",
        "title": "The Concepts Anatomy of OpenClaw",
        "surface": "sidecar"
    },
    "device": {
        "platform": "chrome_ext",
        "locale": "en-US",
        "timezone": "Asia/Hong_Kong"
    }
}
```

### 场景 3：纯聊天（Standalone Web Chatbot / stdio / WeChat）

```json
{
    "schema_version": 1,
    "task": "none",
    "chat": {
        "message": "hello"
    },
    "chat_context": {
        "resource_contexts": []
    },
    "source": {
        "kind": "web",
        "url": "http://localhost:5173/",
        "title": "小记🐹 AI 外语老师",
        "surface": "fullscreen"
    },
    "device": {
        "platform": "web",
        "locale": "en-US",
        "timezone": "Asia/Hong_Kong"
    }
}
```
