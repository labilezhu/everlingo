# Tasks

## 计划的任务

（无）

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"

 - 2026-08-06 | i18n Phase 3（Web 前端 i18n + onboarding step 1 + Me 切换 UI）：后端 `GET /api/user-profile/status` 扩展（needs_setup 含 interface_language 维度 + interface_language/resolved/available_interface_languages）+ 新增 `POST /api/user-profile/interface-language`（校验 + 写 yaml + 显式 bump_prompt_version）+ `/console/me/interface-language` 静态页路由。前端引入 react-i18next + vitest：`web/src/i18n/`（i18n.ts/bootstrap.ts/detect.ts）、`web/src/types/profile.ts`、`web/src/locales/{zh-CN,en}/`（9 namespace）、新 `/console/me/interface-language` 页（InterfaceLanguagePage + main.tsx + html + vite entry）、Me 页「界面语言」入口、8 个既有入口接入 bootstrapI18n（chatbot 按 onboardingTarget 跳 step1/2，/login 跳过 status 请求防 401 循环）、迁移约 200 处硬编码中文文案。测试：tests/test_user_profile_api.py（status 新字段 + TestSetInterfaceLanguage）+ 前端 17 用例（字典一致性/detect/bootstrap/step1 页）。文档：ADR 20260806-phase3-web-i18n-onboarding.md、i18n.md Phase 3 标完成 + 改动清单、ws-console-arch.md §5.2/§5.3/§6、TASKS、release notes。
 - 2026-08-06 | i18n Phase 3 设计阶段：完成 ADR（docs/ADR/20260806-phase3-web-i18n-onboarding.md，解除 ADR 20260801 §9「不引入」决定）+ 更新 docs/i18n/i18n.md Phase 3 节（落点决策、多入口 bootstrap、Editor 纳入范围、写入端点 bump_prompt_version 说明、不在范围澄清）+ ADR 20260801 §9 衔接注释。决策要点：react-i18next + 多入口 bootstrapI18n()、独立页 /console/me/interface-language + 重定向、needs_setup 扩展含 interface_language 维度、POST /api/user-profile/interface-language 动作式风格、显式 bump_prompt_version、Editor 一并 i18n、引入 vitest。
- 2026-08-06 | i18n Phase 2（Chat Agent 兜底文案）：新增 `src/everlingo/i18n/`（messages.py，`MESSAGES` zh-CN/en + `t(key, lang, **kwargs)`，缺失 lang 回退 en、缺失 key 回退 key、`{placeholder}` 占位）；agent.py 3 处（error_retry / ai_unavailable / system_notice_error）、session.py 1 处（error_generic）改为 `t()`，agent 维护 `_interface_lang`、session 从构造 profile 取。system prompt 与前端文案（含 voice 提示、断片通知）不动。tests/test_i18n.py 10 用例。更新 i18n.md Phase 2、release notes v0.1.1。
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

