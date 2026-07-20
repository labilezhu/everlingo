# Current Sprint

## 进行中的任务

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"

- 2026-07-20 | **设计并文档化**: Chrome Extension 选词翻译 sidecar
  - 新建 [chrome-extension-spec.md](/docs/impl-spec/chrome-extension-spec.md)：架构、session 生命周期（tab 级 + device_id 跨 tab）、UI history 持久化（chrome.storage.session）、envelope 构造规则、context.text 提取算法
  - **Schema 扩展**：`SourceWeb.surface` 字段（sidecar/popup/fullscreen 枚举，默认 fullscreen）；`ContextPart.screenshot` 可选字段（ScreenshotPart: data_url + mime）
  - **Agent system prompt**：追加 `task=look_up` 空输入延续语义规则；更新 source 字段说明（当前已落地 plain 与 web）
  - **WebChannel 超时**：`DISCONNECT_GRACE` 从 5 分钟调整为 20 分钟
  - 同步更新 `chat-agent-spec.md`、`web-session-acceptor.md`、`ROADMAP.md`、`phase-2-product.md`
  - 新增测试用例 6 个（surface 默认/显式/无效、screenshot None/roundtrip/序列化）
