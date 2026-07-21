为 [Standalone Web Chatbot](/docs/impl-spec/standalone-web-chatbot.md) 加入类似 [Chrome Extension — Web Sidecar](docs/impl-spec/chrome-extension-spec.md) 的 “翻译” “查词” “聊天” 单选按钮以方便用户准确方便地表达输入内容的意图。

---


src/everlingo/mem/agents/mem_writer_agent.py 中有加载 src/everlingo/mem/vault/templates/default/spec/mem_entry_spec.md 用于帮助 Memory Writer Agent 理解 Chat Agent 输入数据。

现在没有对 Memory Writer Agent 解释：输入的 new_messages 和 context_messages 字段 中的 [Envelope](docs/impl-spec/envelope-impl-spec.md) 是什么。 建议在 Memory Writer Agent 的 prompt 注入 src/everlingo/mem/vault/templates/default/spec/envelope_spec.md ，用类似现在 Memory Writer Agent 注入 mem_entry_spec.md 的实现方法，通过 mcp read 。

---

docs/impl-spec/chrome-extension-spec.md
extension/chrome-extension-impl-spec.md
Chrome Extension 使用 docs/arts/chrome-icon.png 作为图标。需要时，你调整一下分辨率

---


计划作以下增强：
1. Chrome Extension 加入 option:
    - server_url 。 服务端地址。 默认是现在 hard code 的 http://localhost:8000/
2. 现在如果浏览器已经显示了 side panel ，再选词后点击 Chrome Extension 后，没有任何反应。期望是对选词作翻译
3. 选词后，可以鼠标右键菜单发起翻译。
4. Chrome Extension 使用 docs/arts/chrome-icon.png 作为图标。需要时，你调整一下比例

---


请你结合 EverLingo 产品现状和目标，分析一下以下产品设计的合理性，以及你的建议。

计划为产品加入一个新 feature: 作为一个 Chrome Extension ，为任意网页提供翻译和语言学习知识相关的笔记功能。

1. 用户在浏览器选词后出现翻译小工具图标的设计模仿 Google Translate Chrome Extension
2. 用户点击翻译小工具图标后，打开一个 UI 类似 [Standalone Web Chatbot - Web Chatbox Web UI](docs/impl-spec/standalone-web-chatbot.md) 的右则栏 panel(Web Sidecar)
3. 界面成功打开后，注入以下用户输入消息(参考了 docs/impl-spec/envelope-spec.md)：
```json
{
  "schema_version": 1,
  "task": "translate",
  "msg_id": "uuid",
  "chat": {
    "message": "为什么这里不是银行？"
  },
  "selection": {
    "text": "bank" //用户在浏览器选词
  },
  "context": {
    "text": "I sat on the bank of the river." //用户在浏览器选词的同一段落的最多 500 字的上下文。
  },
  "source":   { "kind": "web_sidecar",
                "url": "https://example.com", "title": "..."},
  "device":   { "platform": "chrome_ext", "device_id":"a uuid generated at ext install",
                "locale": "zh-CN", "timezone": "Asia/Shanghai" }
}
```

这里：

- `task`：UI 希望优先完成的任务（ translate、 look_up 等），可以作为 Agent 的先验意图。一般对应 UI 上的不同的按钮
- `selection`、`context`、`page`：浏览器提供的结构化上下文。
- `chat.message`：用户当前输入（可能为空，例如只是点击"翻译"，还没有在聊天中输入文字）。

这样设计有一个很大的优势：**`task` 不需要决定 Agent 的行为，只需要影响 Agent 的默认行为。**

例如：

- `task = translate`，用户又问："顺便解释一下为什么这里用 bank。"——Agent 可以先翻译，再解释。
- `task = look_up`，用户输入：""——Agent 会围绕当前笔记继续工作，而不是重新开始。

换句话说，`task` 更像是**会话上下文（conversation mode）**，而不是一个必须严格执行的 RPC 命令。这种设计与 Chatbot 的交互方式更契合，同时也保留了结构化输入带来的稳定性和可扩展性。

1. Web Sidecar Chat Agent 根据 context ，准确地翻译出 selection 。
2. 用户可以在 Web Sidecar 中通过聊天完成笔记记录。
3. Web Sidecar 小窗口因失去 Focus，或用户点击关闭而隐藏
4. 同一网页中，二次激活翻译工具时，显示之前隐藏的 Web Sidecar



🟢 问题 7：context.text "同一段落最多 500 字" 的实现约束
DOM 中"段落"边界不固定（<p> / <div> / <span> 都可能）。建议：在 Chrome Extension 端实现时定义明确算法——从 selection.anchorNode 向上找最近的 block-level 元素（P/DIV/SECTION/ARTICLE/LI/H1-6），取 textContent 截断 500 字；找不到时退化为 selection 前后各 250 字。这条约束写进 envelope-spec 的 context.text 字段说明里，使前端与后端对齐。
🟢 问题 8：Chrome Extension 权限与商店审核
- activeTab 权限：仅用户主动点击扩展图标时生效，权限最小，但与"选词后自动出现小工具图标"冲突
- host_permissions: all_urls：支持任意网页选词弹图标，但 Chrome Web Store 审核更严，用户也会警惕
- 建议：MVP 用 activeTab + 用户手动点扩展图标激活 sidecar（不自动弹图标）；后续再优化为 host_permissions + 选词弹图标。这也与产品"AI 老师非打扰式"的调性一致。

---

src/everlingo/mem/vault/mcp_server/mcp_server.py:320 create_vault_tool() 中，对于 `spec/` 目录下的文件，需要根据文件内容作不同的 copy 处理：
- *.md 文件：
  - 如果 文件内容开头有 markdown frontmatters ，直接 copy 文件，不要用 compile_prompt
  - 否则，compile_prompt 处理文件内容再 copy （现状）
- 其它文件： 直接 copy 文件

---

先不要写代码和实现。你先把这个重构的 ADR 和设计 ，写到 docs/ADR/20260719-envelope.md

---



你评估一下这个设计的合理性和可行性：

现在从聊天中抽取记忆和写入笔记的流程比较长：

[Chat Agent](docs/impl-spec/chat-agent-spec.md) -> [Memory Extract Agent](/docs/impl-spec/memory-extract-agent-spec.md) -> [Memory Writer Agent](docs/impl-spec/memory-writer-agent-spec.md) 

其中 Chat Agent 到 Memory Extract Agent 的流程增加了复杂度，与有相同数据、类似逻辑重复用 LLM 处理的情况。所以我计划删除 Memory Extract Agent。 直接让 Chat Agent 调用现有的 request_memory_extraction 工具。
request_memory_extraction 工具的入参修改为 ： src/everlingo/mem/vault/templates/default/spec/memory_extract_output_spec.md 。这个工具直接把入参提交给 Memory Writer Agent。 Memory Writer Agent 作异步写入笔记，并在完成后反馈给 Chat Agent ，这个异步写入和反馈和现在一致。


一些实现上的想法：
Chat Agent 不要直接在 system prompt 上写死 src/everlingo/mem/vault/templates/default/spec/memory_extract_output_spec.md， 而应该像 
src/everlingo/mem/agents/mem_writer_agent.py:204 一样，让它在确定要写笔记和抽聊天知识时，才调用 read(path="spec/memory_extract_output_spec.md") 工具动态加载抽取和输出规则。


---

我计划把现在 [Chat Agent](docs/impl-spec/chat-agent-spec.md) 的 "## 用户显式模式指定" 功能删除。原因是：我后面计划引入 json 结构的输入格式去表达用户意图，在应用的 UI 中用户直接在 UI 中通过点击按钮表达意图。


---


如设计文档：
- docs/impl-spec/search/memory-vault-search-spec.md
- docs/impl-spec/search/memory-vault-embedding-spec.md

现在会索引以下目录：$workspace/memory/languages/en/vault 下除了 ./spec 以外的目录

现计划加一个例外：
不要索引 $workspace/memory/languages/en/vault/**/index.md 。即不要索引所有 index.md 文件。



---

现在的 src/everlingo/mem/vault/mcp_server/mcp_server.py:304 的 create_vault_tool() 只 copy 了 src/everlingo/mem/vault/templates/default/spec/*.md  到 $workspace/memory/languages/$lang/vault/spec 。 

计划修改成 copy src/everlingo/mem/vault/templates/default/* （包括子目录和文件） 到 $workspace/memory/languages/$lang/vault/ 

---

评估一下影响和方案：
把 src/everlingo/mem/vault/vault_specs/default 目录重命名为 src/everlingo/mem/vault/templates/default/spec

---

按照设计文档
docs/impl-spec/wiki/wiki-spec.md 

everlingo wiki build 产生了 /home/labile/.everlingo/workspaces/default/.wiki-dist
其中已经有文件 /home/labile/.everlingo/workspaces/default/.wiki-dist/en/items/vocab/ufo.html

但
everlingo wiki serve 后
访问
http://127.0.0.1:8765/items/vocab/ufo 或 http://127.0.0.1:8765/en/items/vocab/ufo
还是 404 了

---


src/everlingo/mem/vault/vault_specs/default/vault_spec.md 文件命名格式：

```text
{slug}--{ulid}.md
```

我打算修改为： {slug}.md 。 你分析一下影响和可行性。文件名冲突的事让 LLM ls / read / write 去处理就好。新文件名会简洁点，人直接浏览文件时，和 url 生成时，更人性化。

---

请分析以下功能和架构设计上的合理性和可行性：

[Chat Agent](docs/impl-spec/chat-agent-spec.md) 的笔记编辑功能，不能修改笔记 markdown 文件的 Markdown Frontmatter。只能修改 body 。 现在计划支持修改所有 Markdown Frontmatter ，除了以下的 Markdown Frontmatter 字段不能修改：
```yaml
ulid: 01JZABD123
slug: pragmatically-answering-yes-or-no-can-easily-lead-to-confusion
type: pragmatics
created_at: 2026-06-22T18:08:00+08:00
timestamp: 2026-06-26T09:15:00+08:00
schema_version: 1
first_seen: 2026-06-22T18:08:00+08:00
last_seen: 2026-06-26T09:15:00+08:00
seen_count: 4
```


---

[Chat Agent](docs/impl-spec/chat-agent-spec.md) 删除和编辑笔记条目的功能已经在代码中实现了，但好像没有把相关的设计，主流程和数据结构，写入文档，帮我更新一下设计文档：
- [Chat Agent](docs/impl-spec/chat-agent-spec.md)
- [Memory Writer Agent](docs/impl-spec/memory-writer-agent-spec.md)

---

请计划一下架构设计和风险点：

我计划实现一个新功能，用户可以在 [Chat Agent](docs/impl-spec/chat-agent-spec.md) 中删除笔记条目（笔记文件），也可以指示 Chat Agent 直接编辑笔记条目的 markdown 主体内容。

流程如下：
1. 用户指示要删除或编辑笔记条目
2. Agent 尝试自动定位目标文件（优先级从高到低）： 
   2.1 Chat Agent 如果能通过 message history 中推断出 `file_path` 就最好（如之前有 Memory Writer 通知的 updated_files，或之前已经定位过文件）
   2.2 如果不能，就通过过 search 找到可选文件集合(top 4)，然后 read 找出最匹配的
3. 发起删除/编辑笔记条操作前，Chat Agent 必须和用户确认上一步自动定位到的目标笔记条目的`title` 和 `item_type(知识点类型)`
4. 如果用户确认，往后操作。否则，如果用户增加了提示信息，按提示 goto 2.1 步继续定位。用户也可以取消操作
5. 同步调用 [Memory Writer Agent](docs/impl-spec/memory-writer-agent-spec.md)(作为 Chat Agent 的 tool) 写入 Vault
6. Memory Writer Agent 同步返回写入结果，由 Chat Agent 转告用户。


Chat Agent 与 Memory Writer 之间的交互数据结构，尽量考虑在现有的 src/everlingo/mem/vault/vault_specs/default/memory_extract_output_spec.md 上扩展。
建议加上以下字段：
```json
{
  "operation": "delete",   // "create"(默认) | "delete" | "edit"
  "file_path": "/items/phrase/the-best-is-yet-to-come--01KXAQCXT331QT41Y6VGSZ2QPW.md",   // delete/edit 专用且必选
  "body": null         // edit 专用且必选：新的 markdown 正文（不含 frontmatter）
}
```

Memory Writer Agent 能不能在原有的 daemon thread 上执行 delete/edit 任务？不希望用多线程 lock 的方案。


---

src/everlingo/mem/agents/mem_writer_agent.py 中 system prompt 的 mem_entry_spec.md 加载，现在是用 PackageSource 。应该修改成与 src/everlingo/mem/agents/mem_extract_agent.py 中 _load_extract_spec_from_vault() 一致的，用 mcp 工具从 vault 中加载的方法。

---

现在的实现，[Chat Agent](docs/impl-spec/chat-agent-spec.md) 不知道 [Memory Extract Agent](/docs/impl-spec/memory-extract-agent-spec.md) 是否有可能触发记忆抽取和后续的[Memory Writer Agent](docs/impl-spec/memory-writer-agent-spec.md)的 Vault 写入。
能不能，由 Chat Agent 去显式（LLM工具或结构输出）去决定是否驱动 Memory Extract Agent ？而不是现在的每轮对话后都驱动 Memory Extract Agent ？ 这然 Agent 间的责任分工可以明确点，不会两个 Agent 不了解对方是否已经响应，而作重复行为。

---

[Chat Agent](docs/impl-spec/chat-agent-spec.md) 加入用户通过对话直接编辑已有 Vault 笔记文件的功能:
- Chat Agent 增加 [MCP Server](src/everlingo/mem/vault/vault_specs/default/memory_extract_output_spec.md) 的 `vault_mcp_write` 工具可用
- 在 Chat Agent 的 System Prompt 中，要强调： 
  笔记的创建和写入，默认应该是 Memory Extract Agent 通过监控你的对话内容去异步更新的。只有在用户在聊天上下文中有明显的直接编辑一个笔记知识条目(文件)的要求时，才按用户要求写笔记文件。

---

2. **通过分析对话，发现用户在 Chat Agent 中直接编辑一个已有笔记知识条目(文件)** ： 这时不应该再由 Memory Extract Agent 去抽取和重复写入。

---

现在的 src/everlingo/mem/agents/mem_extract_agent.py ，是把 $workspaces/memory/languages/$lang/vault/spec/memory_extract_spec.md 注入 system prompt 。

 [MCP Server](docs/impl-spec/vault-mcp/vault-mcp-spec.md) 新增加了一个 compile_prompt(path) 工具，可以加载和预处理带 include 的 markdown prompt 文件。所以 mem_extract_agent.py 的 _load_extract_spec_from_vault 可以简化了。

 另外， mem_extract_agent.py 的  _load_extract_spec_from_package 不需要了，不需要本地 python package 兜底了。

---
src/everlingo/utils/md_prompt_compiler.py 的 compile_prompt() 支持多层 markdown 文件的递归 include 处理吗？

---

为 [MCP Server](docs/impl-spec/vault-mcp/vault-mcp-spec.md) 加入一个 prompt 分类的 tool。它主要作用是对 vault 中的 prompt 文件作预处理后返回:
```yaml
  - name: compile_prompt
    title: compile a file
    description: |
      Compile a prompt file. Expand something like: {{ include [参考 mem_entry_spec.md](./mem_entry_spec.md) }} to the text of target file

    inputSchema:
      type: object
      properties:
        path:
          type: string
          description: Relative markdown file path (leading ``/`` or ``\`` treated as relative to vault root).
      required:
        - path
    outputSchema:
      type: object
      properties:
        content:
          type: string
          description: 文件全文文本。文件不存在时 isError=true + 错误文本，content 为空串。
      required:
        - content
```

其服务端(src/everlingo/mem/vault/mcp_server/mcp_server.py)的实现类似：
```python
compile_prompt(
            path,
            FilesystemSource(base_dir=resolve_vault_path(sess.lang, path)),
        ),
```

这个 tool 同样要依赖于 session.configure 已经配置。

---
