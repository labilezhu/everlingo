
# 产品说明 - phase 2

场景化地记下每一次查询，建立记忆锚点，建立记忆锚点，增加：
- 原屏幕截图，
- 再加入一些辅助记忆又合符用户文化背景的资料卡片

主动定期提供练习回顾，就可以帮助巩固记忆。

## 入口载体：Chrome Extension

Chrome Extension 是 Phase 2 的"场景化查询入口"载体：
- 用户在浏览器任意网页选词 → sidecar panel 内提供翻译/查词/学习问答
- 选词上下文与用户行为数据通过 envelope 协议结构化传递给 Agent
- Agent 根据上下文翻译/解释词义，并通过 `request_memory_extraction` 流程同步写入用户记忆库
- 与"原屏幕截图"目标合流：envelope schema 已预留 `context.screenshot` 字段，后续实现截图后可为每个记忆条目关联原始网页上下文

详见 [Chrome Extension Spec](/docs/impl-spec/chrome-extension-spec.md)。
