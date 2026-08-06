# Envelope 结构化用户输入协议

- 状态：Implemented（2026-07-27）
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
    chat_context: ChatContextPart = ChatContextPart()
    source: SourcePart = Field(default_factory=SourcePlain)
    device: DevicePart | None = None
```

### 字段说明

见： [Envelope 结构化用户输入格式](/src/everlingo/mem/vault/templates/default/spec/envelope_spec.md)


### `source` 字段实现补充

`source` 用 `kind` 字段作为 discriminator。当前定义 6 个 kind，目前仅 `plain` / `web` / `chrome_ext` 被实际使用：

未知 `kind` 值时 pydantic discriminated union 会 raise `ValidationError`。

### `task` 枚举

当前初始值：`translate` / `look_up` / `none`。未来可按需扩展（如 `summarize` / `add_note`）。

## 3. 序列化格式

所有 channel 统一产 `UserInputEnvelope`，Session 层在传给 `MainAgent.ainvoke` 前序列化为 `<envelope>{JSON}</envelope>` 标签包裹的字符串。

### `wrap_plain_text(text: str) -> UserInputEnvelope`

把纯文本输入包装为最小 envelope：
- `task="none"`
- `chat.message = text`
- `source.kind = "plain"`
- `chat_context.resource_contexts = []`

用于 stdio/wechat/web `{text}` 请求。

### `render_envelope_to_message_text(env: UserInputEnvelope) -> str`

把 envelope 序列化为 `<envelope>{JSON}</envelope>` 格式。由 `Session._handle_user_message` 在调用 `agent.ainvoke` 前使用。

## 4. 数据流

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

## 5. 与各 Channel 的关系

| Channel | `recv_envelope()` 实现 | 序列化后 LLM 看到 |
|---|---|---|
| `StdioChannel` | 读 stdin 一行 → `wrap_plain_text(line)` | `<envelope>{"chat":{"message":"用户输入"},"chat_context":{"resource_contexts":[]},...}</envelope>` |
| `WechatChannel` | 从 wechat sdk 队列读消息 → `wrap_plain_text(msg.text)` | 同上 |
| `WebChannel` | 从 `_incoming` 队列读 `UserInputEnvelope`（`source.kind=web` + `surface=fullscreen` 或 `source.kind=chrome_ext` + `surface=sidecar`） | 按前端传入的 envelope 结构（含 `chat_context.resource_contexts`） |

## 6. `ResourceContext` 类型

见 `src/everlingo/gateway/channels/envelope.py` 的 `ResourceContext` discriminated union，三种 kind：
- `vault_file`：Vault Editor 中当前打开的笔记文件
- `web_page`：用户选词的 web 页面
- `selected_text`：用户高亮选定的文本（含段落上下文）。`paragraph_text` 为段落上下文块，最多 500 字，超过时以 `selected_text` 为中心截取，保证包含选词

## 7. 向后兼容

- 现有 web 前端发 `{"text":"..."}` 仍可用：`web_acceptor.py` 检测到 `text` 字段时自动调用 `wrap_plain_text()` 包装为 envelope（`resource_contexts` 为空）。
- `MainAgent.ainvoke` 签名不变（仍收 `MessageEvent(text)`），Agent 代码零改动。
- 用户侧无感知（LLM 通过 system prompt 理解 envelope 格式）。
