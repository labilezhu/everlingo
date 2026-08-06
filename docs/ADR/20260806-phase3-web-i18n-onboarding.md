# ADR: Phase 3 — Web 前端 i18n 框架 + onboarding step 1 + Me 切换 UI

- 状态：Accepted
- 日期：2026-08-06
- 决策参与方：用户、opencode
- 相关文档：
  - [i18n 整体设计](../i18n/i18n.md) §Phase 3
  - [ADR 20260806-interface-language-optional.md](20260806-interface-language-optional.md)（Phase 1）
  - [ADR 20260801-user-onboarding.md](20260801-user-onboarding.md) §9（本 ADR 解除其「不引入」决定）
  - [领域模型](../../DOMAIN.md)
  - [Web Chatbot](../impl-spec/web-chatbot.md)
  - [Vault Editor](../impl-spec/vault-editor.md)
  - [Workspace Console 架构](../impl-spec/workspace-console/ws-console-arch.md)

---

## 1. 动机

Phase 1（[ADR 20260806-interface-language-optional.md](20260806-interface-language-optional.md)）已把 `interface_language` 改为「可选 + OS locale 推断」，建立了「可用界面语言」集合与运行时双访问器。Phase 2 把后端兜底文案集中到 `src/everlingo/i18n/messages.py`。

Phase 3 解决剩下的核心缺口：

1. **Web 前端无 i18n 框架**：`web/` 下 23 个文件、约 200 处硬编码中文文案分散在 Chatbot / Vault Editor / Me / Web Console / Login / Self-Service / Pat 等多个页面，无法随界面语言切换。
2. **`interface_language` 无可视化入口**：[ADR 20260801-user-onboarding.md](20260801-user-onboarding.md) §9 当时决定「不引入界面语言设置入口」，留待未来。Phase 1 给出了运行时兜底，但用户无法在 UI 上显式选择或修改界面语言。
3. **onboarding 缺第一步**：现有 onboarding 是单步流程（仅目标学习语言）。CLI 向导已先选界面语言再选目标语言，Web 端缺少对应的第一步。

## 2. 关联的规则变更与前置解除

### 2.1 解除 ADR 20260801 §9 的「不引入」决定

[ADR 20260801-user-onboarding.md](20260801-user-onboarding.md) §9：

> **`interface_language` 的可视化设置**：本 ADR 不引入界面语言设置入口。`interface_language` 仍由 yaml / 部署模板配置。未来如需，再另起 ADR。

本 ADR 解除该决定：在 Web 端引入界面语言的可视化设置入口（onboarding step 1 + Me 页切换 UI）。CLI 向导（`gateway.py` 首次启动的 `_run_profile_setup`）保持不变，与 Web 端形成两条互斥的首次配置路径，按部署拓扑各自生效。

### 2.2 `needs_setup` 语义扩展

[ADR 20260801](20260801-user-onboarding.md) §5.1 中 `needs_setup = !is_valid`，`is_valid` 仅看 `target_language` 是否「有效且已初始化」。

本 ADR 扩展为：

> **`needs_setup = (!is_valid) OR (interface_language 为空)`**

即「界面语言未显式设置」也触发首次引导。`is_valid` 字段本身**不**扩展（仍只描述 target_language 语义），新增 `interface_language` 字段供前端独立判断分支跳转。

理由：界面语言是用户首次接触产品时最先感知的设置，应在引导用户进入任何中文/英文 UI 前让其显式确认；OS locale 推断仅作为引导页自身的兜底预选，不应让用户静默以推断值进入产品。

### 2.3 `interface_language` 写入端点

[ADR 20260806](20260806-interface-language-optional.md) §4 明确「显式值由 onboarding（Phase 3）或 Me 页切换 UI（Phase 3）写入 yaml」。本 ADR 落实该写入路径：新增 `POST /api/user-profile/interface-language`。

## 3. 概念定义

- **可用界面语言**：`AVAILABLE_INTERFACE_LANGUAGES = ("zh-CN", "en")`（Phase 1 已定义）。显示名复用 `LANGUAGES[code]`。
- **resolved interface language**：`resolve_interface_language(raw)` 的返回值，Phase 1 已定义。运行时消费者（Agent / Gateway）使用 resolved 值；前端在 bootstrap 后用 resolved 值驱动 `i18n.changeLanguage()`。
- **onboarding step 1**：首次引导流程的第一步，让用户选择界面语言。选定后写入 yaml 并重定向到 step 2（现有 `/console/me/target-language`）。
- **onboarding step 2**：现有目标学习语言设置页（ADR 20260801 已实现），保持不变。

## 4. 决策

### 4.1 i18n 框架：react-i18next

引入 `react-i18next` + `i18next`（+ `i18next-browser-languagedetector` 可选）。理由：

- 轻量、生态成熟、支持 Suspense 懒加载 namespace；
- 与现有 Vite + React + shadcn/ui 技术栈无冲突；
- `resolveJsonModule: true` 已在 `tsconfig.json` 启用，可直接 import JSON 字典；
- 两份 JSON 字典合计约 10–30 KB，体积可接受。

字典目录：`web/src/locales/{zh-CN,en}/{common,chatbot,editor,me,onboarding,web-console,login,self-service,pat}.json`，按页面/功能分 namespace，避免单文件膨胀。

### 4.2 多入口 bootstrap

`web/` 是 Vite 多 HTML 入口工程，共有 8 个独立 React root（chatbot、editor、me、target-language、web-console、login、self-service、pat），并非单一 `main.tsx`。i18n.md 原文「前端在 `main.tsx` 启动时拉取」描述不完整。

本 ADR 决定：

- 新建 `web/src/i18n/` 模块（`i18n.ts`、`bootstrap.ts`、`detect.ts`），所有 8 个 `main.tsx` 调用统一入口 `bootstrapI18n()`。
- `bootstrapI18n()` 顺序：
  1. 用 `navigator.language` 启发式推断（`zh*` → `zh-CN`，其它 → `en`）渲染首屏加载占位，避免白屏/中英闪烁；
  2. 调 `GET /api/user-profile/status` 取 `interface_language_resolved`；
  3. 若与启发值不同，`i18n.changeLanguage(resolved)` 校正；
  4. 返回 status 供 `main.tsx` 决定后续路由（onboarding 跳转 / 正常渲染）。
- 启发式仅用于几百毫秒的过渡占位文案，不写入任何持久化存储；最终生效值始终以服务端 resolved 为准。

### 4.3 onboarding step 1 落点：独立页面 + 重定向

新增独立页面 `/console/me/interface-language`，与现有 `/console/me/target-language` 平级，归 Me 页下。引导流程：

1. 任意 `main.tsx` bootstrap 后若 `needs_setup=true`：
   - 若 `interface_language` 为空 → 重定向到 `/console/me/interface-language`（step 1）；
   - 否则 → 重定向到 `/console/me/target-language`（step 2）。
2. step 1 选定并保存 → `POST /api/user-profile/interface-language` → 重定向到 step 2。
3. step 2 行为与 ADR 20260801 §4 完全一致。

理由：

- 与 CLI 向导顺序一致（先界面语言后目标语言）；
- 两步分离，单页复杂度低，且 step 1 的选项列表（可用界面语言）与 step 2（可用目标学习语言）数据来源不同，强行合并会让单页同时承载两套校验；
- 复用现有「Me 子页 + 强制 redirect」模式，结构清晰。

非首次进入（用户从 Me 页主动跳来修改界面语言）也复用此页，仅顶部 banner 文案不同（引导模式 vs 切换模式）。

### 4.4 `needs_setup` 强制引导

`needs_setup` 含 `interface_language` 维度后，首次运行**强制**跳转 step 1，与现有 target_language 强制流程语义一致。用户无法绕过。

OS locale 推断值在 step 1 页面作为预选项高亮（如浏览器是中文环境则预选 zh-CN），用户点确认即写入；用户也可改选 en。推断值不写回 yaml 的不变量（[ADR 20260806](20260806-interface-language-optional.md) §4）不变 —— 必须由用户显式确认才写。

### 4.5 写入端点：`POST /api/user-profile/interface-language`

风格仿现有 `POST /api/target-language/default`（动作式 POST，body `{ lang }`）。**不**采用 RESTful `PATCH /api/user-profile`，与既有端点风格保持一致。

行为：

```
POST /api/user-profile/interface-language
  body: { lang: "zh-CN" }
  → 服务端：
     1. 校验 lang ∈ AVAILABLE_INTERFACE_LANGUAGES，否则 400 "unsupported interface language: <lang>"
     2. load_profile() → model_copy(language.interface_language=lang) → save_profile()
     3. bump_prompt_version()   # 显式触发 Agent 下次 invoke 重建
  → 返回 200 + { interface_language, available_interface_languages: [{code, name}, ...] }
```

**显式调用 `bump_prompt_version()`**：与 `set_default_language`（target language）不同 —— target language 切换依赖 yaml 文件 mtime 变化被 `agent.py:_refresh_agent_if_needed()` 检测；但 interface language 不在 prompt 文件 mtime 监控范围内，必须显式 bump 才能保证 Agent 读取新的 interface_language 重建 system prompt。

**不**回溯给 `set_default_language` 补 `bump_prompt_version()`：该端点已有 mtime 触发机制，且改动它超出 Phase 3 范围（scope creep），可能改变现有重建时机引致回归。

### 4.6 `GET /api/user-profile/status` 扩展

在 [ADR 20260801](20260801-user-onboarding.md) §5.1 现有响应基础上增加三个字段：

```
GET /api/user-profile/status
→ {
    target_language: str,                       # 原有
    is_valid: bool,                             # 原有（仍只看 target_language）
    vault_initialized: bool|null,               # 原有
    needs_setup: bool,                          # 改为：(!is_valid) OR (interface_language == "")
    interface_language: str,                    # 新增：raw，可能 ""
    interface_language_resolved: str,           # 新增：resolve_interface_language(raw)
    available_interface_languages: [           # 新增：供前端直接渲染
      {"code": "zh-CN", "name": "简体中文"},
      {"code": "en", "name": "English"}
    ]
  }
```

`is_valid` 字段语义保持不变（仅描述 target_language 三条件），新增 `interface_language` 字段供前端独立判断 step 1 vs step 2 跳转分支。

### 4.7 Me 页切换 UI

Me 页（`web/src/me/MePage.tsx`）在「目标学习语言」与「Workspace Console」之间新增「界面语言」入口：

- 跳转到 `/console/me/interface-language`（与 onboarding step 1 同页，普通模式）；
- 副标题展示当前 `interface_language_resolved` 对应的 display name（由 `available_interface_languages` 查得）。

切换保存后：

- 前端 `i18n.changeLanguage(lang)` 即时切换 UI 语言，**不刷新页面**；
- 后端写 yaml + `bump_prompt_version()`，下次聊天 invoke 时 Agent 重建并采用新界面语言生成 system prompt。

### 4.8 Vault Editor 一并纳入 Phase 3

i18n.md §Phase 3「不在范围」仅排除 Chrome Extension（Phase 4）。Vault Editor（`web/src/editor/`，约 50+ 处中文）属同一 Vite 工程，与 Chatbot 共享 `i18n` 实例，应一并 i18n 以避免出现「半国际化」状态（聊天界面已切换而笔记编辑器仍中文）。Editor 的 `main.tsx` 同样接入 `bootstrapI18n()`。

### 4.9 前端测试工具链：vitest

`web/` 现无任何前端测试框架。本 ADR 引入 `vitest` + `@testing-library/react` + `@testing-library/jest-dom` + `jsdom`，作为前端测试工具链。

测试覆盖：

- `i18n/dictionaries.test.ts`：所有 namespace 的 zh-CN 与 en key 集合深度相等、占位符 `{{x}}` 一致（防字典漂移）；
- `i18n/bootstrap.test.tsx`：mock `/api/user-profile/status`，断言 `i18n.language` 最终等于 resolved、`needs_setup` 时跳转路径正确；
- `i18n/detect.test.ts`：`navigator.language` 各情形 → 启发值正确；
- `pages/InterfaceLanguagePage.test.tsx`：渲染可用列表、选中后调 POST、跳转目标页。

## 5. 不在本 ADR 范围

- **Chrome Extension i18n**：Phase 4。Extension 是 web 组件的独立副本，将复制 `web/src/locales/` 到 `extension/src/locales/` 并独立引入 react-i18next。
- **Chat Agent 兜底文案 i18n**：Phase 2 已完成。
- **system prompt 本身 i18n**：不做。`_build_system_prompt()` 的中文指令是给 LLM 看的，LLM 会根据 prompt 里的 `interface_lang` 字段自行决定回复语言。
- **`set_default_language`（target language）端点补 `bump_prompt_version()`**：该端点已有 mtime 触发机制，改动超出 Phase 3 范围。
- **多用户共享 workspace 下的 interface_language 隔离**：`interface_language` 是 workspace 级配置，多用户共享一 workspace 时互相可见且互相影响，是既有限制，本 ADR 不解决。

## 6. 替代方案考虑

| 方案 | 否决理由 |
|---|---|
| onboarding step 1 并入现有 target-language 页（单页双步） | 单页同时承载可用界面语言与可用目标学习语言两套列表与校验，复杂度高；且与 CLI 向导「先界面后目标」的两步顺序不一致 |
| onboarding step 1 不强制，仅 Me 页提供入口 | 与现有 target_language 强制引导语义不一致；用户首次接触产品时可能看到非母语界面，体验差 |
| 写入端点用 RESTful `PATCH /api/user-profile` | 与现有 `POST /api/target-language/default` 动作式 POST 风格不符，且需引入 PATCH 处理 |
| 不引入 vitest，仅靠人工回归 | i18n 字典 key 漂移（zh/en 不一致）无护栏，迭代易出错 |
| 首屏加载占位硬编码中文「加载中…」 | 英文用户首屏看到中文，体验差 |
| 首屏加载占位纯符号 spinner 无文字 | 完全规避语言问题，但首屏信息感弱 |

## 7. 实施顺序

1. **后端端点 + 测试**：扩展 `GET /api/user-profile/status`、新增 `POST /api/user-profile/interface-language`（含 `bump_prompt_version()`）；扩展 `tests/test_user_profile_api.py`。
2. **前端 i18n 框架骨架 + vitest + 类型集中**：新建 `web/src/i18n/`（`i18n.ts` / `bootstrap.ts` / `detect.ts`）、`web/src/locales/` 骨架、`web/src/types/profile.ts`、`web/vitest.config.ts`；接入 chatbot 入口验证链路。
3. **onboarding step 1 + Me 入口**：新建 `/console/me/interface-language` 页、`vite.config.ts` 入口、Me 页入口；接入 8 个 `main.tsx` 的 `bootstrapI18n()` 与跳转逻辑。
4. **文案批量迁移**：按 namespace 逐文件迁移（chatbot → editor → web-console → login/self-service/pat）。
5. **ADR + 文档 + Release Notes**：本 ADR、更新 `i18n.md` / `ADR 20260801` §9 衔接说明、`TASKS.md`、`release-notes/v0.1.1/`。

每步跑相关单测（`uv run pytest tests/test_user_profile_api.py -v` + `uv run vitest run`），无需全量。