# Envelope Structured User Input Format

When a user sends a message or performs an UI action in the EverLingo app, structured action-scene context is provided (selected-text, context paragraph, source URL/file, device info, expected user task). Much of this information can serve as the scene in which a knowledge point appears, e.g., the article title and URL where the knowledge point occurred.

## schema

Wrapped in `<envelope>JSON</envelope>` XML and placed in the counterpart message text.

### Field reference

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | int | yes | Currently 1. Used for schema-evolution compatibility |
| `task` | enum | yes | User-preferred task: `translate` / `look_up` / `none`. **It is a preference, not a command** — the LLM may freely decide whether to follow it |
| `chat.message` | str | no | User's natural-language input. May be empty (user only clicked a UI button) |
| `chat_context` | object | no | Context environment while the user acts. Default `{"resource_contexts": []}` |
| `chat_context.resource_contexts` | array | no | List of context resources. **May be an empty array** (pure chat scene). Each item is a tagged union (see `resource_context.kind` below) |
| `source` | tagged union | yes | Source info, discriminated by `kind` |
| `device` | optional | no | Device info, used for personalized explanations |

### `task` enum

Possible values: `translate` / `look_up` / `none`.

### `chat_context.resource_contexts`

The `kind` field is the discriminator for each array element. Currently three `kind`s are defined:

| kind | Use case | Additional fields |
|---|---|---|
| `vault_file` | A note file opened in the Vault Editor | `file_path` |
| `web_page` | The web page where the user selected a word (overlaps with `source` info; used for the LLM to understand context content) | `url`, `title` |
| `selected_text` | Text highlighted/selected by the user | `text`, `start_line`, `start_column`, `paragraph_text` |

#### kind="vault_file"

```json
{
    "kind": "vault_file",
    "file_path": "items/vocab/embedding.md"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `file_path` | str | yes | The vault note entry file path |

#### kind="web_page"

```json
{
    "kind": "web_page",
    "url": "https://example.com/article",
    "title": "Example Article"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `url` | str | yes | The page URL |
| `title` | str | no | The page title |

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

| Field | Type | Required | Description |
|---|---|---|---|
| `text` | str | yes | The selected text content |
| `start_line` | int / null | no | The start line of the selected text (aids locating). `null` when not available |
| `start_column` | int / null | no | The start column of the selected text (aids locating). `null` when not available |
| `paragraph_text` | str / null | no | The paragraph or context block containing the selected text (max 500 characters; when longer, truncate centered on the selected text, ensuring the selected word is included). `null` when not available |

### `source`

`source` is discriminated by the `kind` field. Currently six `kind`s are defined:

| kind | Use case | Additional fields |
|---|---|---|
| `plain` | stdio/wechat requests | no extra fields |
| `web` | Web Chatbot | `url`, `title`, `surface` |
| `chrome_ext` | Chrome Extension web-page word selection | `url`, `title`, `surface` |
| `pdf` | PDF reader plugin | `file_path`, `page_number` |
| `epub` | EPUB reader | `book_id` |
| `ios_app` | iOS app word-selection service | `bundle_id` |

#### kind="web"

```json
    "source": {
        "kind": "web",
        "url": "https://example.com/article",
        "title": "Example Article",
        "surface": "fullscreen"
    },
```

| Field | Type | Required | Description |
|---|---|---|---|
| `url` | str | no | The current page's URL |
| `title` | str | no | The current page's title |
| `surface` | enum | no | Interface type. Possible value: `fullscreen` (Standalone Web Chatbot) |

#### kind="chrome_ext"

```json
    "source": {
        "kind": "chrome_ext",
        "url": "https://chatgpt.com/c/6a5e1033-22cc-83e8-aba3-d1daf5a1dde1",
        "title": "Chrome Extension Sidecar Position",
        "surface": "sidecar"
    },
```

| Field | Type | Required | Description |
|---|---|---|---|
| `url` | str | no | The web page URL where the Chrome Extension captured the selection |
| `title` | str | no | The web page title where the Chrome Extension captured the selection |
| `surface` | enum | no | The surface type. Possible values: `sidecar` (Chrome Extension sidecar position) / `popup` (standalone popup, future) |

#### kind="plain"

```json
    "source": {
        "kind": "plain",
    },
```

### device

Example:
```json
{
    "platform": "chrome_ext",
    "locale": "en-US",
    "timezone": "Asia/Hong_Kong"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `platform` | enum | no | chrome_ext (Chrome Extension) / web (Web Chatbot) |

## Scene examples

### Scene 1: Web Chatbot embedded in the Vault Editor

```json
{
    "schema_version": 1,
    "task": "none",
    "chat": {
        "message": ""
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
        "title": "🐹 Nori Note Editor",
        "surface": "fullscreen"
    },
    "device": {
        "platform": "web",
        "locale": "en-US",
        "timezone": "Asia/Hong_Kong"
    }
}
```

### Scene 2: Chrome Extension Chatbot

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

### Scene 3: Pure chat (Standalone Web Chatbot / stdio / WeChat)

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
        "title": "Nori🐹 AI Language Tutor",
        "surface": "fullscreen"
    },
    "device": {
        "platform": "web",
        "locale": "en-US",
        "timezone": "Asia/Hong_Kong"
    }
}
```