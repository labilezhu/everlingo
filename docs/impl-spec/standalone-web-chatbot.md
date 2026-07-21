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


小记🐹正在思考的提示：
- 在用户发送消息后，“发送” 按钮变为一个轻微的脉冲动画以提示"正在思考中"。在收到回复消息后还原。不要使用现有的前端的 thinking 机制。

尺寸大小：
- Chatbot 对话框可视区域的宽度，应该跟随窗口大小的动态变化动态调整，以最大化用户的可视区域。左右边缘适当留白即可。

### 交互元素
“发送” 按钮：
“发送” 按钮应该调整为更大。上面应该有文字和一个代表 “发送” 的简单 SVG 图形，类似 ➡️。

消息内容的 Markdown 渲染：
默认的文字行距太小，需要加倍。


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
