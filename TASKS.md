# Current Sprint

## 进行中的任务

## 完成的任务
格式：完成日期与时间(北京时间) | 任务描述 。 示例：" - 2026-06-20 19:28 | 生成主入口代码"
- 2026-07-24 XX:XX | **Vault Editor 移动端适配**
  - 断点 `md` (768px)：`< md` 移动端抽屉模式，`>= md` 桌面三栏 flex 不变
  - 按钮文字用 `<span className="hidden md:inline">` 包裹，移动端仅显示图标
  - Header 改 flex 布局，新增汉堡按钮（`Menu` 图标，`md:hidden`），toggle 左栏
  - 左栏/右栏 aside `< md` 时改为 `fixed` overlay + `translate-x` 滑入/滑出
  - 新增 backdrop（`z-30 bg-black/40`），点击关闭所有抽屉
  - 移动端抽屉互斥：打开一个自动关闭另一个
  - Resize 手柄加 `hidden md:block`，移动端隐藏
  - 新增 `useMediaQuery` hook（`matchMedia` + listener）
  - 更新 `docs/impl-spec/vault-editor.md` 移动端小节
- 2026-07-24 XX:XX | **最小化 frontmatter 必选字段 + slug 移出 frontmatter**
  - 方案 B：file_path 作 upsert 主键，ulid 列可空（SQLite UNIQUE 已允许多 NULL，无需 schema 迁移）
  - 代码：indexer._get_existing_rowid / sync.reconcile / watcher._dispatch 改按 file_path 查询
  - 新增 get_by_file_path()；ParsedDoc.ulid 改为 str | None
  - SearchHit.ulid 改为 str | None（protocol.py）
  - slug 移出 frontmatter：从文件名 `Path(rel).stem` 派生（frontmatter 有 slug 仍优先）
  - 移除 `"slug"` 从 _PROTECTED_FRONTMATTER_FIELDS 及相关 prompt
  - 更新 vault_spec.md / kb_items_spec_*.md / search-spec / agent.py / memory_writer_action.py 文档
  - 测试：missing-ulid 改成功 case；新增无 ulid index_file 测试、slug 从文件名派生测试
  - 影响范围：151 vault 搜索测试 + 50 writer agent 测试全部通过
