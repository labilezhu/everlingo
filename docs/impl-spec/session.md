# Session

负责：
loop 阻塞等待 channel 消息，非调用 agent，把 agent 的响应转给 channel。

主要代码示例： `/src/everlingo/gateway/session.py`

## Session 属性
- id : Session 创建时自动生成。用 uuid string
- create_time: 创建时自动生成
- update_time: 最后一次会话的时间，有会话时更新
- title : 保留字段，默认为空，以后实现

## 持久化
Session 会话和 Agent 对话历史，暂时不需要支持持久化保存到文件。

## Channel
参考 [channel.md](/docs/impl-spec/channel.md)