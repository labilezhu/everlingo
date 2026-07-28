
为支持多用户在同一域名下访问不同的 everlingo container 。 有什么建议方案？
不能再依赖 Http Basic Auth 了。要有自己的认证方案和 everlingo container 路由方案。
认证方案暂时可以简单，如用户名密码，但要预留将来 Google SSO 的可能。

我们把这个路由叫 Edge 。 那么应该还需要一个叫 Master 的服务，去管理 container 的 create / start / stop / remove

HTTPS -> HTTP ，我现有 Nginx ，不在 Edge 的范围

除了 Cookie  ，还应该 支持 Authorization: Bearer <token> 。 因为 Chrome Extension 或其它 curl 也会访问 API

包括 Edge Service 和 Master Server ，都应该是运行于 container 中。
---

## 需求
现在的 EverLingo 只有为每个实例指定 workspace 目录的能力，但没有支持多用户的能力。对于后面产品化上线，需要有一个实例同时多用户(同时多 workspace) 的能力。

## 设计

### API 设计
API 层面，我不打算为每个 api 加上 user_id 参数。我想用前端 reverse proxy 分析 auth token ，注入 user_id 这个 http header 。

### 运行期逻辑
实现上，现在一个实例运行时，只支持一个 workspace 。 要修改成，根据 user_id 选择不同的 workspace 目录。

### 数据
有一个 ~/.everlingo/everlingo_master.sqlite 数据库文件，其中 users 表维护用户信息，有以下字段：
user_id, user_name, user_display_name, workspace_dir 

其中  user_name 限制为英文字母和下划线字符集。

增加一个配置文件，叫 ~/.everlingo/everlingo_master.yaml
配置为：
```yaml
sys_setting
  workspace_workspaces: ~/.everlingo/workspaces #默认 ~/.everlingo/workspaces
```

新用户的 users 表的 workspace_dir 字段填入 `$workspace_workspaces/$user_name` 其中  $workspace_workspaces 替换为 everlingo_master.yaml 中的 workspace_workspaces 值

现有的 everlingo.yaml 还是保留在每个用户自己的 workspace_dir 下。


---


考虑一下以下设计的合理性、可行性、设计方案。

为支持更好的聊天上下文选择语义传递。 [envelope](src/everlingo/mem/vault/templates/default/spec/envelope_spec.md) 的数据结构计划作一些重构。

## envelope 格式

主要变更是 selection 和 context 变化。 resource_contexts 变为一个可以为 0 长度的数组。

### 场景1 : Vault Editor 中嵌入的 Web Chatbot

[Vault Editor](docs/impl-spec/vault-editor.md) 中嵌入的 [Web Chatbot](docs/impl-spec/web-chatbot.md)情况下：

```json
<envelope>
{
    "schema_version": 1,
    "task": "none",  
    "chat": {
        "message": "" //用户自然语言输入。可能为空（用户仅点击了 UI 按钮）
    },
    "chat_context": {
        "resource_contexts": [
            { // 选定上下文。 
                "kind": "vault_file",  // 本 resource_context 的类型： vault 笔记条目文件。不能为空
                "file_path": "items/vocab/embedding.md", // vault 笔记条目文件路。不能为空
            },
            {
              "kind": "selected_text", // 本 resource_context 的类型： 用户高亮选定的文本。不能为空
              "text": "structural", // 用户高亮选定的文本内容。不能为空
              "start_line": 19, // 选定的文本的开始行(只是辅助定位作用，无法获取时，json 节点可为 null)
              "start_column": 13, // 选定的文本的开始列(只是辅助定位作用，无法获取时，json 节点可为 null)    
              "paragraph_text": "The embedding of the steel rods in concrete ensures structural stability", // 用户高亮选定的文本所在的段落。无法获取时，json 节点可为 null
            }        
        ],
    },
    "source": {
        "kind": "web",
        "url": "https://home-everlingo.mygraphql.com:6457/editor?lang=en&path=items%2Fvocab%2Fembedding.md",
        "title": "🐹 小记笔记编辑器",
        "surface": "fullscreen"
    },
    "device": {
        "platform": "web",
        "locale": "en-US",
        "timezone": "Asia/Hong_Kong"
    }
}
</envelope>
```

### 场景2 : Chrome Extension Chatbot

```json
<envelope>
{
    "schema_version": 1,
    "task": "translate",  
    "chat": {
        "message": "" //用户自然语言输入。可能为空（用户仅点击了 UI 按钮）
    },
    "chat_context": {
        "resource_contexts": [
            { // 选定上下文。 
                "kind": "web_page",  // 本 resource_context 的类型： web page。不能为空
                "url": "https://blog.mygraphql.com/en/posts/ai/ai-personal-assistant/openclaw-concepts/", // vault 笔记条目文件路。不能为空
                "title": "The Concepts Anatomy of OpenClaw"
            },
            {
              "kind": "selected_text", // 本 resource_context 的类型： 用户高亮选定的文本。不能为空
              "text": "structural", // 用户高亮选定的文本内容。不能为空
              "paragraph_text": "The embedding of the steel rods in concrete ensures structural stability", // 用户高亮选定的文本所在的段落。无法获取时，json 节点可为 null
            }        
        ],
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
</envelope>
```


---
