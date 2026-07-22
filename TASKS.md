# Current Sprint

## 进行中的任务

## 完成的任务
格式：完成日期与时间(北京时间) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"
  - 2026-07-22 12:00 | vault-editor PR 5：FileTree 新建/重命名/删除文件和目录 + 右键/长按 ContextMenu + 行内输入
  - 2026-07-22 17:00 | mem_writer_agent: vault_spec.md 改由 compile_prompt 加载入 system prompt，不再由 LLM 运行时 read(path=...)
  - 2026-07-22 19:00 | 知识点类型唯一事实来源：vault_spec.md，移除代码中 ItemType Literal[5] 硬编码，mem_entry_spec.md 改为引用 vault_spec.md，更新设计文档
  - 2026-07-22 20:00 | editor URL 同步：选中文件后通过 history.replaceState 将 lang+path 反映到地址栏，覆盖 spec 与 TASKS.md
  - 2026-07-22 22:00 | 搜索支持 tag-only（q 可空）+ 搜索模式标签改中文（混合/精确/语义）
