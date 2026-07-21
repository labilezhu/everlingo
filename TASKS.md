# Current Sprint

## 进行中的任务

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"
2026-07-20 20:00 | Chat Agent 提交 mem_entry 添加 DEBUG 日志（create + delete/edit 两路径）- 全量 model_dump
2026-07-20 21:00 | Memory Writer Agent system prompt 注入 envelope_spec.md，解释 new_messages / context_messages 中的 Envelope 格式；重构为共用一条 MCP session 加载两个 spec
2026-07-21 10:00 | Standalone Web Chatbot 加入 task 单选按钮（翻译/查词/聊天），迁移到 envelope 结构化协议；更新相关设计文档
2026-07-21 11:00 | Chat Agent envelope 改为运行期 MCP compile_prompt 加载（与 Memory Writer 一致）；意图识别节新增 envelope.task 作用说明；_call_compile_prompt 迁移到共享的 mem_writer_mcp_client
2026-07-21 12:00 | 修复 7 个测试文件中的 20+ 个失败用例：agent.ainvoke 改用 AsyncMock（test_mem_writer_agent / test_agent_system_notice / test_gateway）；_disable_embedding autouse fixture（conftest.py）；LLM ainvoke try/except（agent.py）；assertions 更新（test_unified_agent.py）；channel.send_sound AsyncMock（test_voice_tool.py）；_cleanup_everlingo_handlers 防止日志处理器泄露（test_log_utils.py）
2026-07-21 16:00 | Vault Editor PR 1：后端 REST→MCP 翻译层。新增 vault_editor_mcp_client.py（per-request 临时 MCP stream）、vault_editor_api.py（/api/vault/* 共 11 个端点 + 错误映射 + rename 复合 + tmp 过滤）、test_vault_editor_api.py（25 个 mock 单测覆盖全线），挂载到 web_acceptor.py
2026-07-21 19:30 | Vault Editor PR 2：Vite 多入口改造 + editor 骨架。web/vite.config.ts 多入口（main+editor）；新增 editor.html、web/src/editor/（main.tsx、EditorApp.tsx 三栏布局+状态总管、FileTree.tsx 递归文件树、MilkdownEditor.tsx textarea 占位、vaultApi.ts fetch 封装、types/vault.ts）；web_acceptor.py /editor 路由 catch-all；test_web_acceptor.py 补 4 个 /editor 路由用例（全量 19 pass）；npm run build 双入口构建通过
2026-07-21 22:00 | FileTree 懒加载：vaultApi.ts tree() 增 path/depth 参数；FileTree.tsx 展开空 children 目录时按需调用 onLazyLoad 拉取子目录；EditorApp.tsx 增 mergeChildren + handleLazyLoad；test_vault_editor_api.py 补 tree(with path) 用例；vault-editor.md 补子目录懒加载说明
2026-07-21 23:00 | Vault Editor PR 3：接入 Milkdown + 双模式切换。新增 @milkdown/kit @milkdown/react 依赖；MilkdownEditor.tsx 重写为 source textarea / WYSIWYG Milkdown 双模式（key-based remount 切文件/模式，listener 插件回传 markdown onChange，skipFirst ref 防初始回调）；EditorApp.tsx 增 mode state + localStorage 持久化、Header 二态 toggle 按钮（Source / WYSIWYG）、mode 透传 + key 驱动 remount；index.css 无新增（editor/main.tsx import prosemirror.css，Milkdown 内联 style 标签）

