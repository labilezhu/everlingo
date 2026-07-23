# Standalone Web Chatbot

Web 前端给用户，一个 Chatbot 的聊天界面。支持 markdown 格式消息的渲染。

成功连接 Chatbot 后端后，session id 将作为前后端建立连接时的标识。

前端代码，静态网页文件位于目录 `/web` 中。

## 通用界面设计风格
尺寸大小：
- 主可视区域的宽度，应该跟随窗口大小的动态变化动态调整，以最大化用户的可视区域。左右边缘适当留白即可。

## Chatbot 界面设计
一个经典的 chatbot 聊天对话框。聊天机器人的名字叫：小记🐹 

消息内容主要是 markdown 文本，markdown 文本消息需要在界面渲染。

### Header

全窗口模式（非 embedded）下，header 右侧显示「笔记编辑器」按钮，点击同窗跳转至 `/editor`（[Vault Editor](vault-editor.md) 入口）。embedded 模式（editor 右侧侧栏）下不显示该按钮。

小记🐹正在思考的提示：
- 在用户发送消息后，“发送” 按钮变为一个轻微的脉冲动画以提示"正在思考中"。在收到回复消息后还原。不要使用现有的前端的 thinking 机制。

尺寸大小：
- Chatbot 对话框可视区域的宽度，应该跟随窗口大小的动态变化动态调整，以最大化用户的可视区域。左右边缘适当留白即可。

### 任务选择（task selector）

header 下方有一行 button group（三个 `Button` 组件，选中态 `variant=default`、未选态 `variant=outline`），与 [Chrome Extension sidecar](chrome-extension-spec.md) 的 `TaskSelector` 视觉一致。

让用户表达输入内容的意图：

| 按钮 | `task` 值 | 说明 |
|---|---|---|
| 翻译 | `translate` | 翻译选词或输入的句子 |
| 查词 | `look_up` | 查询单词释义 |
| 聊天 | `none` | 自由聊天，默认选中 |

选择在组件内持久化（直到用户手动切换），每条消息发送时携带当前 task。

task 语义遵循 [chrome-extension-spec.md §8](chrome-extension-spec.md) 的定义——**用户偏好而非 RPC 命令**，Agent 可自由决定是否遵循。

### 交互元素
“发送” 按钮：
“发送” 按钮应该调整为更大。上面应该有文字和一个代表 “发送” 的简单 SVG 图形，类似 ➡️。

消息内容的 Markdown 渲染：
默认的文字行距太小，需要加倍。

### Envelope 字段填充规则

Standalone Web Chatbot 切换到结构化 `{envelope}` 格式发送消息（不再使用 `{text}` legacy 格式）。字段填充规则：

| 字段 | 填充来源 |
|---|---|
| `schema_version` | 固定 `1` |
| `task` | TaskSelector button group 选择 |
| `chat.message` | 输入框文本 |
| `selection.text` | `""`（web chatbot 无选词场景） |
| `context.text` | `""` |
| `source.kind` | `"web"` |
| `source.surface` | `"fullscreen"`（与 sidecar 的 `"sidecar"` 区分） |
| `source.url` | `window.location.href` |
| `source.title` | `document.title` |
| `device.platform` | `"web"` |
| `device.locale` | `navigator.language` |
| `device.timezone` | `Intl.DateTimeFormat().resolvedOptions().timeZone` |

`selection.text` / `context.text` 留空，因为 standalone web chatbot 没有页面选词上下文。

### 示例

用户打开聊天页面，选择「翻译」，输入 "bank is a financial institution"：

```json
{
  "envelope": {
    "schema_version": 1,
    "task": "translate",
    "chat": { "message": "bank is a financial institution" },
    "selection": { "text": "" },
    "context": { "text": "" },
    "source": {
      "kind": "web",
      "surface": "fullscreen",
      "url": "http://localhost:5173/",
      "title": "小记🐹 AI 外语老师"
    },
    "device": {
      "platform": "web",
      "locale": "zh-CN",
      "timezone": "Asia/Shanghai"
    }
  }
}
```


## 前端技术选型

使用组件库:
- Vite
- React
- TailwindCSS
- shadcn/ui
- react-markdown

### Vite 
用途
项目构建工具（开发服务器 + 打包工具）。

负责:
项目创建
本地开发服务器
热更新（HMR）
生产环境打包

作用范围，仅负责：
开发
构建
打包

不负责：
UI
聊天
Markdown
SSE

### React
用途：
前端 UI 框架。

负责：
页面状态管理
聊天消息列表
输入框
页面布局
SSE 消息事件处理

推荐组件结构：
```
src/

components/

  ChatWindow.tsx
  MessageBubble.tsx
  MarkdownRenderer.tsx
  ChatInput.tsx

services/
  sseClient.ts

types/
  chat.ts
```

### TailwindCSS
用途:
CSS 样式框架。

负责：
布局
颜色
边距
字体
响应式设计

用于:
聊天窗口：
左右布局
消息气泡
输入框样式
滚动区域

不负责:
组件逻辑
Markdown
SSE

### shadcn/ui
通用 UI 组件库。
基于：

TailwindCSS
+
Radix UI

生成源码到项目中。不是运行时依赖。

负责：
- Button
- Input
- Textarea

### react-markdown

用途

渲染 AI 返回的 Markdown。
