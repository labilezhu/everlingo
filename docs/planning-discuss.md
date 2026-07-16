
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
