# Envelope 结构化用户输入格式

用户发出消息或 EverLingo 应用 UI 操作时，提供了结构化操作场景上下文（选词文本、上下文段落、来源 URL/文件、设备信息、用户期望任务）。其中很多信息可以作为知识点出现的场景，如知识点出现的相关文章标题和 url 等等。

## schema

格式举例：
```json
<envelope>
{
    "schema_version": 1,
    "task": "translate",
    "chat": {
        "message": ""
    },
    "selection": {
        "text": "不会"
    },
    "context": {
        "text": "老用户可能还是左侧：如果用户以前修改过 Side Panel 的位置，Chrome 会保留这个偏好，不会自动改回来。",
        "kind": "paragraph",
        "screenshot": null
    },
    "source": {
        "kind": "web",
        "url": "https://chatgpt.com/c/6a5e1033-22cc-83e8-aba3-d1daf5a1dde1",
        "title": "Chrome扩展侧边栏位置",
        "surface": "sidecar"
    },
    "device": {
        "platform": "chrome_ext",
        "locale": "en-US",
        "timezone": "Asia/Hong_Kong"
    }
}
</envelope>
```

用 <envelope>. (json)..</envelope> XML 包装，放入对方消息文本中。

### json 字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `schema_version` | int | 是 | 当前为 1。用于 schema 演进兼容 |
| `task` | enum | 是 | 用户偏好任务：`translate` / `look_up` / `none`。**是偏好不是命令**，LLM 可自由决定是否遵循 |
| `chat.message` | str | 否 | 用户自然语言输入。可能为空（用户仅点击了 UI 按钮） |
| `selection.text` | str | 否 | 用户选中的词/短语。纯聊天场景（stdio/wechat）恒为空 |
| `context.text` | str | 否 | 选词周围的上下文（最多 500 字），用于消歧（如 bank 在河岸 vs 银行） |
| `source` | tagged union | 是 | 来源信息，用 `kind` 区分 |
| `device` | optional | 否 | 设备信息，用于个性化释义 |

### `task` 枚举

当前初始值：`translate` / `look_up` / `none`。

### `source`

来源信息。

`source` 用 `kind` 字段作为 discriminator。 当前定义 5 个 kind：

| kind | 使用场景 | 专属字段 |
|---|---|---|
| `plain` | stdio/wechat/web `{text}` 请求 | 无额外字段 |
| `web` | Chrome Extension 网页选词 | `url`, `title` |
| `pdf` | PDF 阅读器插件 | `file_path`, `page_number` |
| `epub` | EPUB 阅读器 | `book_id` |
| `ios_app` | iOS app 选词服务 | `bundle_id` |

未知 `kind` 值时 pydantic discriminated union 会 raise `ValidationError`。


#### kind="web"

```json
    "source": {
        "kind": "web",
        "url": "https://chatgpt.com/c/6a5e1033-22cc-83e8-aba3-d1daf5a1dde1",
        "title": "Chrome扩展侧边栏位置",
        "surface": "sidecar"
    },
```

字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `url` | str | 否 | Chrome Extension 当前抓取选择内容的网页 URL  |
| `title` | str | 否 | Chrome Extension 当前抓取选择内容的网页 title  |
| `surface` | enum | 否 | Chrome Extension 的界面类型。可选：sidecar  |

#### kind="plain"

```json
    "source": {
        "kind": "plain",
    },
```
无其它字段