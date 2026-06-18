# Stdio Channel

一个 [Channel](/docs/impl-spec/channel.md) 的实现。
- `send` 的消息输出到 stdout，可考虑直接用 `print` 函数。写入 stdout 的消息内容后面，需要增加一个换行符。
- `recv` 来自 stdin 的一行文字，可考虑用 `input` 函数。

实现应该在 `/src/everlingo/gateway/channels/stdio_channel.py`