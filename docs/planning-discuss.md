
把 docs/arts/chrome-icon.png 进行 png 缩放，replace 现在 extension/public/icons 目录下的三个文件

---

为 [Vault Editor](docs/impl-spec/vault-editor.md) 和 standalone [Web Chatbot](docs/impl-spec/web-chatbot.md) 均没有 favorite icon

---

[Vault Editor](docs/impl-spec/vault-editor.md) 的两个侧边栏， Files 和 [Web Chatbot](docs/impl-spec/web-chatbot.md) 。 在移动设备界面下，均不能 scroll 。 scroll 操作错误传到主栏上了。

---

[Web Chatbot](docs/impl-spec/web-chatbot.md)现在的界面设计主是要为桌面浏览器。在 移动设备 如 iphone 上没有优化，如：
- 按钮上的文字说明在移动设备上本可以自动隐藏

你的建议用前端响应式处理的方法？ 类似 [Vault Editor](docs/impl-spec/vault-editor.md)  ？


---

[Vault Editor](docs/impl-spec/vault-editor.md) 现在的界面设计主是要为桌面浏览器。在 移动设备 如 iphone 上没有优化，如：
- 按钮上的文字说明在移动设备上本可以自动隐藏
- 则边栏应该可以完全 toggle 隐藏


你的建议是为移动设备做一个独立的界面，还是用前端响应式处理的方法？

---


docs/impl-spec/search/memory-vault-search-spec.md
docs/impl-spec/search/memory-vault-embedding-spec.md

现在的 对被索引的 markdown 文件是不是有很多要求？ 如 markdown frontmatter:
```yaml
ulid: 01JZABD123
slug: pragmatically-answering-yes-or-no-can-easily-lead-to-confusion
type: pragmatics
title: 语用学上，回答 Yes 或 No 时容易混淆
description: 语用学上，回答 Yes 或 No 时容易混淆
description_in_target_lang: 'Pragmatically, answering "Yes" or "No" can easily lead to confusion.'
created_at: 2026-06-22T18:08:00+08:00
timestamp: 2026-06-26T09:15:00+08:00
schema_version: 1
first_seen: 2026-06-22T18:08:00+08:00
last_seen: 2026-06-26T09:15:00+08:00
seen_count: 4
tags: 
  - pragmatics
first_source_kind: web
first_source_url: "https://blog.mygraphql.com/en/posts/ai/ai-life-automatic/ai-job-subcribe/"
first_source_title: "AI-Based Job Position Watching from Company Career Pages(PoC) - Part 1"
```
中，哪些是必须的。我计划列出最少的 frontmatter 要求，把减少不必要的字段的依赖。这样用户自己维护 markdown 文件才比较方便。


---

[Vault Editor](docs/impl-spec/vault-editor.md) 的 直观模式下编辑文件，能不能支持点击 markdown 内链接后，在新 tab 中打开链接？ 现在 是点击没有反应。

---

[Vault Editor](docs/impl-spec/vault-editor.md) 的 File Explorer 不应该显示 ".xyz" 这种操作系统 hide 级的目录和文件，如 ".git" 。 建议直接在后端实现中不返回这类文件和目录。

---

[Vault Editor](docs/impl-spec/vault-editor.md) 的 File Explorer 现在显示的是目录名和文件名。这些 slug 格式的名字对用户不友好。现在修改为：
- 目录显示名：如果目录下有一个 index.md 文件，文件中有 `title` 这个 frontmatter。就使用这个作为目录在 File Explorer 中的显示名。否则显示名同目录名
- 文件显示名：如果文件中有 `title` 这个 frontmatter。就使用这个作为文件在 File Explorer 中的显示名。否则显示名同文件名

前端应该记录下目录和文件的显示名和实际名。

考虑到生成一棵 File Explorer 树不能在文件数量多时，过次调用后端 api 。 你看看后端 api spec 要不要为这个显示的调整页调整。



---

## 需求
为 [Chat Agent](docs/impl-spec/chat-agent-spec.md) 的输出的消息内笔记 file path 部分内容，加上 到 [Vault Editor](docs/impl-spec/vault-editor.md) 的 link 。

## 设计

PR1 & PR2 刚才已经实现，现在计划 PR 3 设计和实现。但设计时要顾及以后。请你也对设计的合理性与可行性作讨论

### PR 1: 加入配置项

见：everlingo.example.yaml:48 :
```yaml
plugins:
  channels:
    channel_web: # Web Session Acceptor 配置
      listener: # 监听地址
        port: 8000 # 默认 8000
        interface: localhost  # 默认 localhost
      public_address: # 浏览器访问地址。如外网或 https 反向代理访问时配置
        base_url: http://localhost:8000 # 默认 用上面的 listener 的生效配置生成： http://$interface:$port
```

- 同步修改文档： user-docs/reference/configuration.md 与 docs/impl-spec/web-session-acceptor.md 
- 修改相关配置加载和使用的代码

### PR 2: Chat Agent 输出笔记文件地址时，包含到 editor 的 link (后端)



[Chat Agent](docs/impl-spec/chat-agent-spec.md) 的 src/everlingo/agents/agent.py 的 system prompt 插入：
- `## 基本配置` 下插入： 
    ```markdown
    - public_address_base_url (浏览器访问地址) : 运行期的生效配置
    ```
- `## 笔记 Vault / 知识库 ` 下插入：
    ```markdown
    输出笔记文件地址时使用 markdown link 。 格式是: `[file_path](http://localhost:8000/editor?lang=en&path=items%2Fidiom%2Feating-your-own-dog-food.md)`。 其中 
    - http://localhost:8000 来自 基本配置：public_address_base_url
    - lang 的值来自 基本配置：target_lang
    - path 的值是 原始的 file_path 进行 url encode 后的结果
    ```

### PR 3: Chat Agent 输出笔记文件地址时，包含到 editor 的 link (前端)

需求：

[Web Chatbot](docs/impl-spec/web-chatbot.md) 在用户点击消息中的链接时：
- 如果是 Web Chatbot 嵌入到 [Vault Editor](docs/impl-spec/vault-editor.md) 时，把 链接 url 传给 Vault Editor 。 Vault Editor 收到后，打开文件。
- 其它情况下，默认是在浏览器新窗口(Tab) 打开链接

设计：

浏览器里的 Web Chatbot 不应该直接依赖于 Vault Editor 。 应该是 Web Chatbot 提供一个 addLinkListener 接口，让 Vault Editor 在初始化嵌入 的 Web Chatbot 时注册。这个 LinkListener 的接口举例如下：
```js
bool/*true: 停止继续处理 link*/ onUserClickLink(url); 
```
当用户在 Web Chatbot 点击 link 时，先让调用 onUserClickLink 。当 onUserClickLink 返回 true 时，Web Chatbot 本身不再处理链接事件。

Vault Editor 在收到事件后:
1. 判断 URL origin 部分(如 http://localhost:8000) 是否与自身地址相同
   1. 相同的话，抽取链接的 path 部分， url decode ，然后打开文件，而不是全页面的刷新。 onUserClickLink 返回 true
   2. 不同的话，onUserClickLink 返回 false



---

在 [Editor](docs/impl-spec/vault-editor.md) 的 search 条件中，可选的 tag 应许随笔记的 tag 的增加页可以同步变化。要在 tag 列表后，增加一个小刷新按钮吧

--

在 [Editor](docs/impl-spec/vault-editor.md) 的 page header 上的 源码/直观/保存 三个按键，移动到 editor 中显示当前打开的文件 path 的 panel 的右则上可以吗？

---

在 [Editor](docs/impl-spec/vault-editor.md) 的 page header 上增加： 
- 一个按钮 “呼叫小记”，按下之后，在 page 右边栏打开一个可调宽度的 [Standalone Web Chatbot](docs/impl-spec/web-chatbot.md)
- 一个按钮 “转到小记”，按下之后，跳转到 [Standalone Web Chatbot](docs/impl-spec/web-chatbot.md)，即 '$host:/'

---

在全窗口(非嵌入[Editor](docs/impl-spec/vault-editor.md)) 的 [Standalone Web Chatbot](docs/impl-spec/web-chatbot.md) 的 header 上，增加一个按钮 “笔记编辑器”，按下之后，跳转到 [Editor](docs/impl-spec/vault-editor.md)，即 '$host:/editor'


---

在 [Editor](docs/impl-spec/vault-editor.md)

---

[Editor](docs/impl-spec/vault-editor.md) 
- editor 有两种编辑模式: Source & WYSIWYG 。 要界面中用这么专业的术语不好，请修改成 ： 源码 & 直观

- editor page header 标题文字修改
```html
<div class="flex items-center gap-2"><svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-file-code size-5 text-muted-foreground" aria-hidden="true"><path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"></path><path d="M14 2v5a1 1 0 0 0 1 1h5"></path><path d="M10 12.5 8 15l2 2.5"></path><path d="m14 12.5 2 2.5-2 2.5"></path></svg><span class="text-sm font-semibold text-foreground">Vault Editor</span></div>
```
换成 page header 中间放置的： 🐹 小记笔记编辑器  
不需要 svg 图了。

---

在 [Editor](docs/impl-spec/vault-editor.md) 的 WYSIWYG 编辑模式下，当 markdown 文档编辑区域获得 focuse 时，辑区域区域会被画上一个灰色的框：
Chrome DevTools 看到
<div contenteditable="true" translate="no" class="ProseMirror editor" role="textbox">
变成了
<div contenteditable="true" translate="no" class="ProseMirror editor ProseMirror-focused" role="textbox">

我的想法是，能不能不要这个灰色的框？ 即不要修改上面的 css class 了。
---

在实现了以下功能后：
[Editor](docs/impl-spec/vault-editor.md)  的 file explorer 加入一个 header 工具栏，其中暂时只有一个刷新按钮，功能就是用户手工刷新 file explorer 内容。
发现一个问题：
点 file exploer 上的刷新按钮后，未展开的目录，就再也展不开了。而用浏览器的 refresh 后，又恢复正常了。

---


计划一下：
 [Editor](docs/impl-spec/vault-editor.md) ： 
 - 搜索支持只用 tag 搜索，可以不输入搜索内容
 - 搜索 界面现在 用 H / E / S 三个字母表达三种搜索方法。建议修改成用中文吧，一般人不知识  H / E / S 是什么意思。且说明一下是搜索模式
---

src/everlingo/mem/agents/mem_writer_agent.py 现在是由 LLM 通过工具 read(path="spec/vault_spec.md") 加载 vault_spec.md 的。其实 mem_writer_agent 是一定要加载 vault_spec.md 的。所以不如直接用 mcp 的 compile_prompt(path="spec/vault_spec.md") 调用，加载入 system prompt 好了。

请同步更新 docs/impl-spec/memory-writer-agent-spec.md

---

现在的 [Vault](src/everlingo/mem/vault/templates/default/spec/vault_spec.md) 知识分类和目录结构，除了在 src/everlingo/mem/vault/templates/default/spec 下的 spec 文档中，可以由用户修改。 但有的还是在代码中写死的，如：
- src/everlingo/mem/agents/mem_entries.py:15
- src/everlingo/tools/request_memory_extract.py:12

我计划让高级用户可以通过修改 $workspace/memory/languages/$lang/vault/spec/vault_spec.md 去修改 Vault 的`知识点类型`和目录结构

现在发现 src/everlingo/mem/vault/templates/default/spec/mem_entry_spec.md:28 也有 `知识点类型` 的声明，和 vault_spec.md 重复了，应该只有一个 source of truth.

现在的 indexer 能有效地对用户自由定义的 $workspace/memory/languages/$lang/vault/items 目录结构作全文和语义索引吗？
---

我的想法有变，以以下为准。

说说你的想法，看看设计是否合理：

EverLingo 会由用户产生大量的 markdown 格式的笔记文件 [Vault](src/everlingo/mem/vault/templates/default/spec/vault_spec.md) ，我计划开发一个在浏览器上，让用户可以直接可视化编辑这些 markdown 文件。

需求：
- 编辑器的形态偏好哪种？ 源码 / WYSIWYG 两种编辑模式切换
- 编辑范围是哪些文件？ markdown 文件是用户笔记，间接通过 docs/impl-spec/vault-mcp/vault-mcp-spec.md 的 read/write 写入。加入 file explorer 与 搜索功能。
- UI：要带 文件树 + 搜索。

设计要点：
- 与 现有的 [Standalone Web Chatbot](docs/impl-spec/web-chatbot.md) 共用一个 http server，服务 编辑器的静态网页部分和 API/MCP 转发部分。即 http://localhost:8000/
- 文件读写走哪条路径？ http://localhost:8000/mcp -> python 后端简单转发 -> [Indexer: Vault MCP Spec](docs/impl-spec/vault-mcp/vault-mcp-spec.md)。 前端 JS 不直接访问 Indexer MCP 。 由后端转发
- 前端的技术 stack 类似 ： docs/impl-spec/web-chatbot.md
- 你看看： 编辑器的前端代码，是否与 Standalone Web Chatbot 放在一起？


---


我改变主意了，Markdown 笔记浏览和编辑，应该和 [Standalone Web Chatbot](docs/impl-spec/web-chatbot.md) 有界面上的整合交互（以后可能会在同一网页，现在是 Chatbot 可以产生 link 到 markdown 笔记的链接。所以，笔记浏览和编辑的功能，还是和 Standalone Web Chatbot 在同一个端口，同一个进程更合理？

---

现在的 [Chat Agent](docs/impl-spec/chat-agent-spec.md) 只是在 system prompt 中 hardcode 了 [Envelope 结构化用户输入格式](src/everlingo/mem/vault/templates/default/spec/envelope_spec.md) 的说明。
现计划修改成与 [Memory Writer Agent](docs/impl-spec/memory-writer-agent-spec.md)  一样，运行期 mcp read 合并到 system prompt。 并在 “## 用户意图识别” 中，说明 envelope 中 task 的作用。

---

为 [Standalone Web Chatbot](/docs/impl-spec/web-chatbot.md) 加入类似 [Chrome Extension — Web Sidecar](docs/impl-spec/chrome-extension-spec.md) 的 “翻译” “查词” “聊天” 单选按钮以方便用户准确方便地表达输入内容的意图。

---


src/everlingo/mem/agents/mem_writer_agent.py 中有加载 src/everlingo/mem/vault/templates/default/spec/mem_entry_spec.md 用于帮助 Memory Writer Agent 理解 Chat Agent 输入数据。

现在没有对 Memory Writer Agent 解释：输入的 new_messages 和 context_messages 字段 中的 [Envelope](docs/impl-spec/envelope-impl-spec.md) 是什么。 建议在 Memory Writer Agent 的 prompt 注入 src/everlingo/mem/vault/templates/default/spec/envelope_spec.md ，用类似现在 Memory Writer Agent 注入 mem_entry_spec.md 的实现方法，通过 mcp read 。

---

docs/impl-spec/chrome-extension-spec.md
extension/chrome-extension-impl-spec.md
Chrome Extension 使用 docs/arts/chrome-icon.png 作为图标。需要时，你调整一下分辨率
