# Current Sprint

## 进行中的任务


## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"

- 2026-07-05 00:00 | 修正 `documents.lang` 数据来源：从 Markdown Frontmatter `lang` 改为 vault 文件路径前缀 `{lang}/`（如 `en/items/...` → lang=en）。改动：`events_index.py` 新增 `KbItemFileMeta` + `parse_kb_item_path()`；`indexer.py` kb item 分支用 path 解析 lang（frontmatter `lang` 字段忽略），USER.md 分支 lang=None；更新 `test_mem_vault_search_indexer.py`（修正 2 处断言 + 删 2 处冗余 frontmatter lang + 新增 2 个测试）；`memory-vault-search-spec.md` schema 注释补「来源：vault 文件路径前缀」。
- 2026-07-04 00:00 | 向量检索增加 Markdown Frontmatter 字段 chunk：`indexer.py` 新增 `_frontmatter_chunks()`，为 `kind='item'` 的 `headword`/`title`/`intro_in_interface_lang`/`intro_in_target_lang` 各生成一个 `section_kind='frontmatter'` 的 chunk（`chunk.text = "key: value"`，`char_offset=NULL`），排在 body chunk 之前；同步更新 `rebuild_fts()`；更新 `memory-vault-search-spec.md` 与 `memory-vault-embedding-spec.md`；新增 7 个测试于 `test_mem_vault_search_indexer.py`。

