

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