# Current Sprint

## 进行中的任务

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"
 - 2026-07-16 18:52 | create_vault: 从只 copy spec/*.md 改为递归 copy templates/default/*（spec/*.md 走 compile_prompt，其余 raw copy）；返回字段 spec_written → files_written（int）；同步更新设计文档
 - 2026-07-16 18:59 | create_vault: spec/*.md 有 frontmatter 的原样 copy 保留 frontmatter，不再走 compile_prompt（compile_prompt 会剥离 frontmatter）；用 split_frontmatter 检测；补 spec/index.md 断言
 - 2026-07-16 21:15 | fix: _parse_write_confirmation 因 AIMessage.content 为 list 类型时报 AttributeError（list 无 .strip 方法）；添加 list→str 归一化处理并跳过空内容
 - 2026-07-16 22:04 | 排除 vault 中所有 index.md 文件不索引（vault 保留文件名，类别导航页 / wiki builder 临时根 index）；一并修复 CLI reindex 路径的内联 tmp/ 过滤改用 is_excluded_vault_file 统一收口，补上 spec/ 与 VAULT_SPEC.md 的 CLI 缺漏；同步更新设计文档
 - 2026-07-18 23:37 | 删除 Chat Agent「用户显式模式指定」功能（/dict /translate / /help 命令与 SystemMessage 注入）；联动删除 ExtractInput.intent_mode / MemoryEntry.user_intent / 下游 vault spec user_intent 字段；为后续 JSON 输入 UI 意图表达方案让路
 - 2026-07-18 23:37 | fix: test_mem_vault_search_embedding_store.py 中 _insert_one_doc 的 file_path 硬编码为 x.md 导致 UNIQUE 冲突，改为使用 ulid 生成唯一路径；test_wiki.py 中 test_generate_index_md 断言未匹配 _LANG_NAMES 新增的 emoji 前缀
