# Tasks

## 计划的任务

（无）

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"

 - 2026-08-06 | i18n Phase 1（配置层）：interface_language 由「必选」改「可选」。models.py 新增 `AVAILABLE_INTERFACE_LANGUAGES`（=zh-CN/en，显示名复用 LANGUAGES）与 `resolve_interface_language()`（精确命中 → OS locale 归一化命中 → 前缀 zh*/en* → 兜底 en）；`UserProfile.validate()` 删「界面语言未设置」+ 新增「非空但不支持」校验；`is_complete()` 仅看 target_language。setting.py 新增 `load_resolved_profile()`（双访问器，推断值不写回 yaml）；agent.py / gateway.py 运行时改用 resolved。gateway CLI 向导界面语言选择限到可用集。文档：docs/i18n/i18n.md（路线图）、ADR 20260806-interface-language-optional.md、DOMAIN.md、configuration.md、everlingo.example.yaml、6 处部署模板移除硬编码 zh-CN。tests/test_setting.py 新增 11 用例（含推断/容错/不污染 yaml/一致性断言）。
 - 2026-08-06 | Embedding 请求同样携带应用标识 headers：ai_embedding.py 的 AIEmbedding 构造 OpenAIEmbeddings 时加入与 llm.py 一致的 default_headers（User-Agent / HTTP-Referer / X-Title）
 - 2026-08-04 | Me 页底部加版本信息；release 流程纳入源码版本号同步（MePage.tsx / ws_master / ws_router）
- 2026-08-04 | 【目标学习语言设置页】添加「重新初始化」按钮：MCP reset_vault 工具 + API 端点 + 前端按钮，重置 spec/ 目录（覆盖写入模板文件）
- 2026-08-04 | 笔记编辑器语言下拉默认选中 everlingo.yaml 的 target_language（GET /api/vault/langs 新增 default 字段，前端据此预选）
- 2026-08-04 | Web PWA 白屏修复：统一 fetch 401 兜底跳 /login（apiFetch.ts）+ React ErrorBoundary + 复活认证复检（useAuthRecheck）+ HTML 缓存头 no-store / assets immutable（web_acceptor.py、ws_router/app.py）；ADR 20260804-web-cache-control.md
 - 2026-08-04 | 修复 gateway 重启后 SSE session_expired 死循环：session_expired 时自动清空 sessionStorage 持久化会话并重建新 session，不再依赖「重新加载」按钮
 - 2026-08-04 | 修复跨页跳转（chatbot ↔ Me 等按钮）后回来每次都新建 chat session：session_expired 自动清空 sessionStorage 的设计在页面卸载/导航期间 EventSource 误触发 onerror 时会把存储同步清掉，导致跨页回来无法复用 sid。回退为 spec 规定的「手动重启」UI（显示「会话已过期 [重新开始]」提示条，用户点击才 clearChatState + 重建），同步更新 ADR 20260804 第 4 项
- 2026-08-04 | 笔记编辑器文件树中根层 spec/ 与 events/ 目录默认收起，减少视觉干扰
- 2026-08-06 | 笔记编辑器移除语言选择下拉框：统一使用 everlingo.yaml 的 target_language（user_profile.language.target_language）；未配置时阻断编辑并引导到 /console/me/target-language；后端与 agent prompt 保持不变

 - 2026-08-06 | 修复选词翻译 `paragraph_text` 不带选词的问题：段落超 500 字时改为以选词为中心截取（envelope_spec.md 要求的语义）。Chrome 扩展 `content/extract.ts` 按 spec §6.3 重写为 `extractContextText`（TreeWalker 计算选区偏移避免空白折叠错位），`ChatWindow.tsx` 的 executeScript `SNAPSHOT_FN` 与 sidecar 自身选区分支同步改为中心截取；Web Chatbot `MilkdownEditor.tsx` selectionRef 用 ProseMirror `$from.parentOffset` 定位后中心截取。新增 `centerWindow` 纯函数 + `extractContextText` DOM mock 单测（extract.test.ts，10 用例）；同步修正 chrome-extension-impl-spec.md §8 伪代码（原为简单头部截断，与 spec 矛盾）

