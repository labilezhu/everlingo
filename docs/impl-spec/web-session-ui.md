# Web Session UI

Web 前端给用户，一个 Chatbot 的聊天界面。支持 markdown 格式消息的渲染。

成功连接 Chatbot 后端后，session id 将作为前后端建立连接时的标识。

前端代码，静态网页文件位于目录 /web 中。


## Chatbot 界面设计
一个经典的 chatbot 聊天对话框。聊天机器人的名字叫：小记🐹 

消息内容主要是 markdown 文本，markdown 文本消息需要在界面渲染。

界面需要有动态元素提示：
- `小记🐹正在思考`

- 在收到后端推送的 `send_typing_hint` 后，显示`小记🐹正在思考`。在收到后端推送的 `stop_typing_hint` 后，不再显示 `小记🐹正在思考`。
- 在收到后端的 `send` 

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
