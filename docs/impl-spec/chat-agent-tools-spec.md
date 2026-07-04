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
