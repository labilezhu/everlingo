

结合：
- docs/impl-spec/worksplace/memory-vault-spec.md
- src/everlingo/mem/vault/vault_spec.md
- docs/impl-spec/search/memory-vault-search-spec.md
- docs/impl-spec/search/memory-vault-embedding-spec.md
评估一下
docs/impl-spec/worksplace/workspace.md 中 “### Workspace 目录结构” 中 重构 workspace 的目录结构 的架构上的合理性和可行性。


---

评估这个改动的合理性与可行性：
为让 vault 格式兼容 [Google Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/knowledge-catalog/raw/refs/heads/main/okf/SPEC.md) 按顺序修改相关文档和代码：
1. 把 src/everlingo/mem/vault/vault_spec.md 中的 “Markdown Frontmatter 通用字段” 字段移动合并到 src/everlingo/mem/vault/kb_items_spec.md 中的 “增加 Markdown Frontmatter 字段”
2. 把 kb_items_spec.md 中的 “增加 Markdown Frontmatter 字段” 中的 `updated_at` 重命名为 `timestamp` 。 字段说明为: update time, 使用格式 ISO 8601 。 
3. kb_items_spec.md 中的 “增加 Markdown Frontmatter 字段” 中的 `intro_in_interface_lang` 字段，重命名为 `description` 字段 。 

---

我设计 indexer 的 MCP Server 服务。打算：
- `search` 工具： 把 docs/impl-spec/search/search-api-spec.md 中 “##### 示例 3 - hybrid 混合搜索”  加到 docs/impl-spec/vault-mcp/valut-mcp-spec.md 引用的 docs/impl-spec/vault-mcp/valut-mcp-spec-tools.yaml 中的 `search` 工具。

请分析这样做的合理性，以及架构上的计划


---

现在的 [Memory Extract Agent](docs/impl-spec/memory-extract-agent-spec.md) 有个问题：
- 记住的知识内容应该来源于 [Chat Agent](docs/impl-spec/chat-agent-spec.md) 的对话消息，但现在有的内容是 Memory Extract Agent 自己产生的。
  - 如： 
    - 环境设置：目标学习语言是 英语
    - 用户消息：你记住 god 这个单词
    - Chat Agent 返回消息： 已经提交记录请求
    - Memory Extract Agent： 什么知识点都没 extract 。

分析一下问题的原因。


---

讨论一个问题。我现在计划为 [Chat Agent](docs/impl-spec/chat-agent-spec.md) 加上记忆(Vault) 的召回功能。如果用户显式要求查看之前的笔记/记忆的话。
实现架构设计方案上，因我觉得把所有信息包括记忆 Vault 的结构，hardcode 写入 system prompt 的话。可能影响 Chat Agent 的 LLM ，长的 system prompt 也难维护。有两个不同的方向：
1. Chat Agent 在需要搜索/获取笔记时，动态加载笔记相关的 Prompt(如 src/everlingo/mem/vault/vault_spec.md) 可以用类似 Agent Skills 的方式动态加载。
2. 写一个 Vault Memory Retrieval Agent 。 Chat Agent 把要获取的记忆要点告诉 Vault Memory Retrieval Agent ， 由 它同步返回。
3. vault_spec 的工具，返回 vault_spec 文本。要 Chat Agent 在加载 vault 文件前阅读

---

讨论一下。我计划为现有的 [Valut MCP](docs/impl-spec/vault-mcp/valut-mcp-spec.md) 加入一个 Agent 可以获取 [完整的 Valut 结构说明](src/everlingo/mem/vault/vault_spec.md) 的 tool/resource 。

---

为 [Valut MCP](docs/impl-spec/vault-mcp/valut-mcp-spec.md) 加入两个 tools:
- list valuts
  - 工具说明：列出当前 workspace 里所有的 valut。 
  - 返回：已经建立目录的，`目标学习语言`代码，即 valut 名，也就是 目录名。$workspace/memory/languages/ 下的目录列表。
- create valut
  - 工具说明：新建和初始化一个指定 `目标学习语言` 的 valut 目录。 
  - 实现说明： 
    1. 新建立 $workspace/memory/languages/$lang 目录
    2.  src/everlingo/mem/vault/vault_spec.md src/everlingo/mem/agents/mem_writer_agent.py