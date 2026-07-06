

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