# Current Sprint

## 进行中的任务

## 完成的任务
格式：完成日期与时间(北京时间) | 任务描述 。 示例：" - 2026-06-20 19:28 | 生成主入口代码"
  - 2026-07-22 12:00 | vault-editor PR 5：FileTree 新建/重命名/删除文件和目录 + 右键/长按 ContextMenu + 行内输入
  - 2026-07-22 17:00 | mem_writer_agent: vault_spec.md 改由 compile_prompt 加载入 system prompt，不再由 LLM 运行时 read(path=...)
  - 2026-07-22 19:00 | 知识点类型唯一事实来源：vault_spec.md，移除代码中 ItemType Literal[5] 硬编码，mem_entry_spec.md 改为引用 vault_spec.md，更新设计文档
  - 2026-07-22 20:00 | editor URL 同步：选中文件后通过 history.replaceState 将 lang+path 反映到地址栏，覆盖 spec 与 TASKS.md
  - 2026-07-22 22:00 | 搜索支持 tag-only（q 可空）+ 搜索模式标签改中文（混合/精确/语义）
  - 2026-07-22 23:00 | editor FileTree header 工具栏 + 刷新按钮（整树重拉）；DRY 重构 4 处重复 tree 重拉
  - 2026-07-23 10:00 | 修复刷新后已懒加载目录无法再展开：将 loaded 标记从组件 useRef 移到 Entry.loaded 数据字段，刷新/切语言时随整树重拉重置，重新点开按需懒加载
  - 2026-07-23 11:00 | editor header 改造：标题居中「🐹 小记笔记编辑器」去掉 svg 图标；模式切换文案 Source/WYSIWYG → 源码/直观；同步 editor.html 标题与 vault-editor.md 文档术语
  - 2026-07-23 12:00 | editor header 增加「呼叫小记」（右侧打开可调宽 chatbot 侧栏，session 常驻）与「转到小记」（跳转 /）按钮
  - 2026-07-23 14:00 | standalone chatbot header 增加「笔记编辑器」按钮，点击跳转 /editor；仅非嵌入式模式显示；更新设计文档
  - 2026-07-23 15:00 | 将 editor header 上的「源码/直观」模式切换和「保存」按钮移至编辑区上方文件路径面板右侧；header 仅保留 lang selector、标题、呼叫小记、转到小记
  - 2026-07-23 16:00 | SearchBar tag 候选列表增加刷新按钮（RefreshCw），手动重拉 list_tags 以同步笔记 tag 增删；tags 区块常驻显示（无 tag 时显示「暂无 tag」提示）；修复 tag 切换 lang 时 filter 闭包 bug；更新 vault-editor.md 设计文档
  - 2026-07-24 10:00 | PR1: 加入配置项 plugins.channels.channel_web（listener + public_address.base_url）；新增 WebListener/WebPublicAddress/ChannelWeb/Channels/Plugins 模型；setting.py 新增 get_web_listener/get_web_public_base_url helper；gateway.py WebSessionAcceptor 接入 listener 配置；更新 configuration.md / web-session-acceptor.md / vault-editor.md 文档；新增 55 项 plugins 配置测试，全量 566 通过
  - 2026-07-24 11:00 | PR2: Chat Agent 输出笔记文件地址时用 markdown link 指向 Vault Editor。agent.py _build_system_prompt 新增 public_address_base_url 参数；## 基本配置 加 target_lang_code 与 public_address_base_url 两行；## 笔记 Vault / 知识库 节新增 ### 笔记文件地址的输出格式 子节（示例 URL 用 base_url + lang=代码 + url-encoded path）；_refresh_agent_if_needed 通过 setting.get_web_public_base_url() 获取并传入；更新 chat-agent-spec.md；新增 TestNoteFileLinkFormat 5 项测试，agent 相关 116 项测试通过
  - 2026-07-24 12:00 | PR3: Web Chatbot 链接点击行为。MarkdownRenderer 自定义 `<a>` 组件加 `target="_blank"` + `LinkListenerContext`；ChatWindow 新增 `linkListener` prop 经 Context 下发；EditorApp 新增 `openFileContent`/`loadFile`/`handleChatLinkClick`，嵌入时拦截 `/editor` 同源链接同窗打开文件（切 lang + 重拉 tree + read），独立 chatbot / 外链 / 非 `/editor` 路径回退新 Tab；更新 vault-editor.md / web-chatbot.md 文档
  - 2026-07-24 13:00 | Chrome Extension sidecar 链接新 Tab 打开：MarkdownRenderer 自定义 `<a>` 组件加 `target="_blank" rel="noopener noreferrer"`；不引入 LinkListenerContext（sidecar 无宿主嵌入场景）；更新 chrome-extension-impl-spec.md 文档
  - 2026-07-24 17:00 | FileTree 显示名优化：后端 tree 端点遍历 entries 读 frontmatter 前 4KB 注入 `title`（文件取自身 title，目录取 index.md 的 title，index.md 文件自身不注入 title）；前端 Entry 类型增 `title` 字段，FileTree 显示用 `title ?? name`（index.md 永远显示 index.md）；更新 vault-editor.md 文档与 TASKS.md
  - 2026-07-24 18:00 | WYSIWYG 模式点击 markdown 内链接支持：单击 `<a>` 触发链接跳转。外链新 tab 打开；同源 `/editor?lang=...&path=...` 及 vault 相对/绝对路径在当前编辑区加载（未保存 confirm、跨 lang 自动切换）；Source 模式不做处理。更新 vault-editor.md 文档与 TASKS.md
