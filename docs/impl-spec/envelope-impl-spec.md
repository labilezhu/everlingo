# Envelope 结构化用户输入协议

- 状态：Implemented（2026-07-19）
- 相关文档：
  - [ADR: 引入 UserInputEnvelope 统一结构化用户输入协议](../ADR/20260719-envelope.md)
  - [Channel](./channel.md)
  - [Session](./session.md)
  - [Chat Agent](chat-agent-spec.md)
  - [Web Session Acceptor](./web-session-acceptor.md)

---

## 1. 背景

产品下一阶段要支持 Chrome Extension 选词翻译、PDF 阅读器插件、iOS app 选词查询等"选词查询表面（selection surface）"。这些设备的共同特征是：Channel 在产出用户消息时，能同时提供结构化上下文（选词文本、上下文段落、来源 URL/文件、设备信息、用户期望任务）。

原有 `Channel.recv() -> str | None` 纯文本协议无法承载这些结构化字段，故引入 `UserInputEnvelope` 统一协议。

## 2. schema

实现代码：`src/everlingo/gateway/channels/envelope.py`

### `UserInputEnvelope`

```python
class UserInputEnvelope(BaseModel):
    schema_version: int = 1
    task: TaskKind = "none"
    chat: ChatPart = ChatPart()
    selection: SelectionPart = SelectionPart()
    context: ContextPart = ContextPart()
    source: SourcePart = Field(default_factory=SourcePlain)
    device: DevicePart | None = None
```

### 字段说明

见： [Envelope 结构化用户输入格式](/src/everlingo/mem/vault/templates/default/spec/envelope_spec.md)


### `source` 字段实现补充

`source` 用 `kind` 字段作为 discriminator。当前定义 5 个 kind，目前仅 `plain` 被实际使用（stdio/wechat/web `{text}` 请求产 `plain`），其余为未来预留：

未知 `kind` 值时 pydantic discriminated union 会 raise `ValidationError`。

### `task` 枚举

当前初始值：`translate` / `look_up` / `none`。未来可按需扩展（如 `summarize` / `add_note`）。

## 3. 序列化格式

所有 channel 统一产 `UserInputEnvelope`，Session 层在传给 `MainAgent.ainvoke` 前序列化为 `<envelope>{JSON}</envelope>` 标签包裹的字符串。

例如一个 web 翻译请求的序列化输出：

```json
<envelope>
{
  "schema_version": 1,
  "task": "translate",
  "chat": {
    "message": "为什么这里不是银行？"
  },
  "selection": {
    "text": "bank"
  },
  "context": {
    "text": "I sat on the bank of the river.",
    "kind": "paragraph"
  },
  "source": {
    "kind": "web",
    "url": "https://example.com",
    "title": "Example Article"
  },
  "device": {
    "platform": "chrome_ext",
    "locale": "zh-CN"
  }
}
</envelope>
```

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


格式要点：
- **XML 标签 `<envelope>`**：标记结构化数据的起止边界，避免与用户纯文本输入（如 `{"name":"mark"}`）混淆。stdio/wechat 的纯文本输入被 `wrap_plain_text()` 包装后同样带此标签。
- **JSON 体**：`model_dump_json(ensure_ascii=False)` 序列化，无额外空格。
- **标签内无业务语义**：所有业务字段在 JSON 内，标签仅作边界标记。

## 4. 工具函数

### `wrap_plain_text(text: str) -> UserInputEnvelope`

把纯文本输入包装为最小 envelope：
- `task="none"`
- `chat.message = text`
- `source.kind = "plain"`

用于 stdio/wechat/web `{text}` 请求。

### `render_envelope_to_message_text(env: UserInputEnvelope) -> str`

把 envelope 序列化为 `<envelope>{JSON}</envelope>` 格式。由 `Session._handle_user_message` 在调用 `agent.ainvoke` 前使用。

## 5. 数据流

```
Channel (任何子类)
  └→ recv_envelope() → UserInputEnvelope | None
       └→ Session._channel_listener
            └→ UserMessage(envelope=env)
                 └→ Session._handle_user_message(ev)
                      ├→ 日志: [ChatAgent] IN envelope={JSON}
                      ├→ text = render_envelope_to_message_text(ev.envelope)
                      └→ agent.ainvoke(MessageEvent(text=text))
```

## 6. 与各 Channel 的关系

| Channel | `recv_envelope()` 实现 | 序列化后 LLM 看到 |
|---|---|---|
| `StdioChannel` | 读 stdin 一行 → `wrap_plain_text(line)` | `<envelope>{"chat":{"message":"用户输入"},...}</envelope>` |
| `WechatChannel` | 从 wechat sdk 队列读消息 → `wrap_plain_text(msg.text)` | 同上 |
| `WebChannel` | 从 `_incoming` 队列读 `UserInputEnvelope` | 按前端传入的 envelope 结构 |

## 7. 向后兼容

- 现有 web 前端发 `{"text":"..."}` 仍可用：`web_acceptor.py` 检测到 `text` 字段时自动调用 `wrap_plain_text()` 包装为 envelope。
- `MainAgent.ainvoke` 签名不变（仍收 `MessageEvent(text)`），Agent 代码零改动。
- 用户侧无感知（LLM 通过 system prompt 理解 envelope 格式）。
