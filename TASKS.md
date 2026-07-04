# Current Sprint

## 进行中的任务


## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"

- 2026-07-04 00:00 | 向量检索增加 Markdown Frontmatter 字段 chunk：`indexer.py` 新增 `_frontmatter_chunks()`，为 `kind='item'` 的 `headword`/`title`/`intro_in_interface_lang`/`intro_in_target_lang` 各生成一个 `section_kind='frontmatter'` 的 chunk（`chunk.text = "key: value"`，`char_offset=NULL`），排在 body chunk 之前；同步更新 `rebuild_fts()`；更新 `memory-vault-search-spec.md` 与 `memory-vault-embedding-spec.md`；新增 7 个测试于 `test_mem_vault_search_indexer.py`。

