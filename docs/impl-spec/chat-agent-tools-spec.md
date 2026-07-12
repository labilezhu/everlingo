# Tools


## langchain tool 实现

langchain tools 的写法：

```python
@tool("$toolset_$function_name:")  # 即加入 toolset name 作为前缀
def search(query: str) -> str:
    """Search the web for information."""
    return f"Results for: {query}"
```

每个 toolset 应该对应一个独立的 python 文件。文件应该放于 `/src/everlingo/tools` 目录。如 `/src/everlingo/tools/conf_manager.py`。

 `/src/everlingo/tools/tools.py` 应该是一个可以获取所有 tools 的注册表。为 langchain agent 提供总的 tools 列表。
 ```python
 def get_tools() -> list:
        return [x,y,z]
    return []
 ```

### tools 调用日志
每个 tool 的调用，均需要记录日志。logging level 为 debug。内容和格式如下：
```log
tool_name: xyz , parameters: argName1=argValue1,... , return: xyz
```

- **logger**：`everlingo.tools`（`src/everlingo/tools/__init__.py` 的 `log_tool_call` 装饰器），经 `everlingo` 父 logger propagate 到 gateway 进程的 FileHandler，写入 `$workspace/logs/everlingo.log`。
- **默认 level**：依赖 `sys_setting.logging_setting.log_level`，默认 `debug`；用户可在 `everlingo.yaml` 调高到 info/warn/error，此时 debug 日志被过滤（行为预期，非 bug）。
- **装饰器位置**：`src/everlingo/tools/__init__.py:log_tool_call`，应应用于所有 toolset 工具的每个公开函数。`voice_speak` 为工厂函数 `make_voice_speak_tool` 生成的 inner function，同样需 `@log_tool_call("voice_speak")`。


# Toolsets(工具集)

以下包括多个 toolset(工具集)。 

## 管理配置 - conf_manager

toolset name: conf_manager
toolset description: 管理配置

### functions

#### get_schema
function name: get_schema
function description: 获取配置元信息描述与schema 
returns: yaml 格式的配置示例。直接返回 [/everlingo.example.yaml](/everlingo.example.yaml) 内容。

#### get_config
function name: get_config
function description: 查询配置
returns: 返回当前生效的 yaml 格式的配置文件内容

#### set_config
function name: set_config
function description: 修改多个配置项目。
parameters:
    configToBeMerged: string
returns: 
    config: string 。 成功 merged 后的 yaml 格式的配置文件内容。
    error: string。 如果失败，返回原因。

可以管理的配置和相关描述与约束，见 [configuration.md](/docs/impl-spec/configuration.md)。 一定要对用户的输入进行配置约束检查。            

调用例子：
configToBeMerged :
```yaml
sys_setting:
    openai_model: deepseek
user_profile:
    language:
        interface_language: zh-CN
        target_language: en
    background:
        hobbies: 历史与文艺
    dictionary_definition_style: |
        - 词意
        - 词源解释和历史
        - 词性（动词，名词……）如果是动词提供过去式，过去分词    
```

## 系统时间 - clock

tool name: clock
tool description: 系统时间


### functions

#### get_datetime
function name: get_datetime
function description: 返回当前的系统时间
returns: string . 格式：日期与时间(Shanghai timezone) 。示例： `2026-06-20 19:28:59` 

## 用户自由偏好笔记 - user_doc

toolset name: user_doc
toolset description: 管理用户自由偏好笔记 (USER.md)

管理 `$workspace/memory/USER.md` 文件。文件内容为 Markdown 自由文本，会被注入到 Agent 的 system prompt。参考 [DOMAIN.md](/DOMAIN.md) 中 `用户自由偏好笔记 - USER.md` 一节。

### functions

#### user_doc_get
function name: user_doc_get
function description: 读取当前 USER.md 全文
returns: string 。文件不存在时返回空串。

#### user_doc_set
function name: user_doc_set
function description: 整体覆盖写入 USER.md。写入前自动把旧内容备份到 `USER.md.bak`（若旧文件存在）。成功后递增 prompt 版本号，触发下次 invoke 时刷新 system prompt。
parameters:
    content: string 。要写入的完整内容。
returns: string 。写入的内容。

**使用约定**：Agent 更新 USER.md 时应先 `user_doc_get` 读取当前内容，在其基础上修改，再 `user_doc_set` 写回完整内容，避免片段覆盖丢失。

## 语音发送 - voice

toolset name: voice
toolset description: 发送语音消息

### 设计说明

voice_speak 工具通过工厂函数 `make_voice_speak_tool(channel)` 创建，绑定到特定 channel 实例。
仅在 `ChannelMetadata.supported_sound_media_format` 包含 `"mp3"` 时，工具才会被加入 Agent 的 tool 列表。

工具是同步的，内部 fire-and-forget 调度异步 TTS+send 到后台线程（独立 event loop）。
失败只记日志 + stderr，不影响主流程。

### functions

#### voice_speak
function name: voice_speak
function description: 向用户发送该段文本的语音朗读。仅在用户偏好或显式要求时调用。
parameters:
    text: string 。要朗读并发送给用户的文本。
returns: string 。固定返回 `"voice scheduled"`。

**调用准则**（由 system prompt 注入）：
- 用户在「个性化偏好设置」中表达偏好发送语音
- 用户在对话中显式要求发音/朗读/听一下
- 朗读内容优先级：查词时的单词发音、翻译时的短句示范发音
- 仅当用户显式要求「朗读整段回复」时，才发送整段回复的语音

**异步机制**：
- 工具调用后立即返回 `"voice scheduled"`，不等待 TTS 完成
- TTS 合成与 channel.send_sound 在后台线程异步执行
- 失败通过 `logger.error` + `print(file=sys.stderr)` 记录

**TTS 抽象**：
- 当前使用 `EdgeTTSProvider`（基于 `edge-tts` 库）
- 接口 `TTSProvider.synthesize(text, fmt="mp3") -> bytes`
- 未来可扩展 OpenAI / OpenRouter 等 TTS provider

## vault 记忆库（只读）

toolset name: vault_mcp
toolset description: 只读查询用户的记忆库（Memory Vault）。含搜索与文件系统操作。

### 实现方式

由 Vault MCP Server（[vault-mcp-spec.md](/docs/impl-spec/vault-mcp/vault-mcp-spec.md)）提供该工具集。Chat Agent 通过 `mcp_vault_connection`（`mem_writer_mcp_client.py`）打开长连接，加载 `CHAT_AGENT_WANTED_TOOLS` 子集（只读）。工具前缀 `vault_mcp`。

共 5 个只读工具。非 MCP Streamable-Transport 工具（不依赖 MCP 进程也可测试的）除外，本工具集均依赖 MCP Server 进程。

### tools

工具的原型/入参/出参和 vault-mcp-spec 中定义的 fs 工具与 search 工具完全一致，前缀映射如下：

| Chat Agent 工具名 | 映射到 Vault MCP 工具 | 功能 |
|---|---|---|
| `vault_mcp_search` | `search` | 混合搜索（hybrid = 全文 + 语义），默认 `mode=hybrid` |
| `vault_mcp_read` | `read` | 读取 vault 文件内容（支持 `VAULT_SPEC.md`） |
| `vault_mcp_ls` | `ls` | 列出 vault 目录 |
| `vault_mcp_find` | `find` | 按 glob 模式查找 vault 文件 |
| `vault_mcp_grep` | `grep` | 全文搜索正文 |

详见 [vault-mcp-spec-tools.yaml](/docs/impl-spec/vault-mcp/vault-mcp-spec-tools.yaml) 中对应工具的 `inputSchema` / `outputSchema`。

### 工具使用准则

- 所有 path 参数均为相对 vault 根的路径（如 `items/vocab`）。
- `search`：建议默认 `mode=hybrid`，`lang` 不传（自动绑定到会话 lang）。
- 首次使用前可先 `vault_mcp_read(path="VAULT_SPEC.md")` 了解 vault 目录结构与文件规范。
- 仅读不写；写入由 `request_memory_extraction` 工具触发异步抽取-写入流程。

## 记忆抽取触发 - request_memory_extraction

toolset name: request_memory_extraction
toolset description: 显式触发记忆抽取，将本轮对话中的知识点异步写入记忆库。

### functions

#### request_memory_extraction
function name: request_memory_extraction
function description: 请求对本轮对话进行记忆抽取。调用后立即返回，抽取异步执行不阻塞回复。
parameters:
    reason: string 。触发原因：user_explicit_request / correction / other。
    note: string 。可选的语义提示，给下游 Extract Agent 参考，不指定具体 entries 内容。
returns: string 。固定返回 "memory extraction requested"。

**调用准则**：
- 用户明确要求记住（"记住 X"、"帮我记下 X"）→ reason="user_explicit_request"
- 纠正用户目标学习语言错误且用户未预期到 → reason="correction"
- 其他值得记录的情形 → reason="other"
- 调用前必须已在本轮回复中产出知识点实际内容（释义/解释/用法/举例）
- 与 target_lang 无关的闲聊 / 纯查词翻译无纠正 / 用户偏好类 → 不调用

**实现机制**：
- 工具执行体仅设置 MainAgent 内部的 pending 标记，不在工具调用循环内直接 submit。
- 实际 submit 由 `MainAgent.invoke()` 末尾统一处理，确保 `new_messages` 切片正确。
