# 目标学习语言设置页

Web 前端给用户一个可视化选择**默认目标学习语言**并初始化笔记库（vault）的设置页。解决新用户首次使用时只能「手改 yaml + 手跑工具」的问题。

设置页入口 URL：`http://localhost:8000/console/me/target-language`。

- 决策依据：见 [ADR 20260801](/docs/ADR/20260801-user-onboarding.md)。
- 归属：Workspace Console 的 **Me 页**直接子页（`/console/me/target-language`）。目标学习语言是**用户偏好**而非 channel 运维，归 Me 页比归 Workspace Console 的 channels admin 更贴切。
- 与 [Vault Editor](/docs/impl-spec/vault-editor.md) 共用同一 HTTP server（[Web Session Acceptor](/docs/impl-spec/web-session-acceptor.md)），同一 origin，不同前端入口（Vite 多入口构建）。

## 概念

- **支持的目标学习语言**：固定 5 种 `en / ja / zh-CN / fr / de`（`src/everlingo/models.py` 的 `LANGUAGES` 字典 key），产品固定能力，不可由用户增删。
- **默认目标学习语言**：`user_profile.language.target_language` 的取值，最多一个。
- **笔记库已初始化**：该 lang 出现在 Vault MCP `list_vaults` 返回结果中（即 `$workspace/memory/languages/$lang/` 存在并已注册到 indexer）。
- **有效的默认目标学习语言配置**：同时满足
  1. `target_language` 非空
  2. 取值 ∈ 支持的目标学习语言 5 种
  3. 该 lang 的笔记库已初始化

  （不再要求 ≠ `interface_language`，二者可相同，见 ADR §2。）

## 后端设计

代码位于 `src/everlingo/gateway/user_profile_api.py`，`APIRouter(tags=["user-profile"])`，经 `src/everlingo/gateway/web_acceptor.py` 挂载。三个端点均**不依赖认证**（单用户本地拓扑同样可用，使首次引导在两种拓扑下都生效）。

复用 `vault_editor_mcp_client.mcp_session_workspace()` 建立 MCP session（`list_vaults` / `create_vault` 均为 workspace 级工具，不需要 `session.configure`）。`IndexerOfflineError → HTTP 503` 的包装模式同 `vault_editor_api.py` 的 `_workspace()`。

### GET /api/user-profile/status

返回默认目标学习语言配置状态（§3 三条件判定）：

```
→ {
    target_language: str,           # 当前取值，空字符串表示未设置
    is_valid: bool,                 # 非空 + ∈ LANGUAGES + vault 已初始化 三条件全满足
    vault_initialized: bool|null,   # list_vaults 结果；indexer 不可达时 null
    needs_setup: bool               # = !is_valid
  }
```

- `target_language` 为空 / 非法 → `is_valid=false`、`needs_setup=true`。
- `list_vaults` 不可达 → `vault_initialized=null`、`is_valid=false`、`needs_setup=true`（**不返回 503**，降级为「未知」）。

### GET /api/target-language/list

列出全部 5 种语言及当前状态：

```
→ {
    languages: [
      {
        code: "en",
        name: "English",
        is_default: true,
        vault_initialized: true,   # bool；indexer 不可达时 null
        disabled: false,            # 是否禁用选中（仅 vault_initialized=null 时为 true）
        disabled_reason: null       # "笔记库状态未知（indexer 不可达）" 等
      },
      ...
    ],
    current_default: "en"
  }
```

- `indexer 不可达`时所有行 `vault_initialized=null`、`disabled=true`、`disabled_reason` 非空（**不返回 503**）。

### POST /api/target-language/default

把某语言设为默认目标学习语言。服务端依次：

1. 校验 `lang ∈` 5 种支持语言，否则 **400**。
2. `list_vaults` 查该 lang 是否已建：
   - 已建 → 直接写 yaml。
   - 未建 → **静默**调 `create_vault(lang)` → 成功后写 yaml。
   - `list_vaults` / `create_vault` 不可达 → **503**，不写 yaml。
3. `save_profile()` 写 `user_profile.language.target_language` 到 `$workspace/everlingo.yaml`。
4. 返回 200 + 新 list（同 GET `/api/target-language/list` 结构）。

写回 yaml 走 `src/everlingo/setting.py` 既有 `load_profile()` + `model_copy(update=...)` + `save_profile()` 范式。

### 单测

`tests/test_user_profile_api.py`（12 用例），复用 `test_vault_editor_api.py` 的 mock 范式（`_MockCtx` / `_fake_result` / `_error_result` / patch `_workspace`）+ `test_setting.py` 的 `monkeypatch + tmp_path` workspace 隔离：

- status 五态：未设置 / 合法已初始化 / 合法未初始化 / 非法语言 / indexer 不可达（`null` 降级）。
- list：5 种全列、`is_default` 单选、`vault_initialized` 三态、indexer 不可达全禁用。
- default：合法已建（不调 `create_vault`）、合法未建（`list_vaults → create_vault → save_profile` 调用顺序）、**合法已为默认但未建（仍走 `list_vaults → create_vault → save_profile`）**、非法 lang 400、indexer 不可达 503 且 profile 不变。
- yaml 写回：真实 `everlingo.yaml` 文件断言 `target_language` 更新。

## 前端设计

### 构建入口与路由

- `web/vite.config.ts` `rollupOptions.input` 增加 `'target-language': path.resolve(__dirname, 'target-language.html')`。
- 新增 `web/target-language.html`（结构同 `web/me.html`，引用 `/src/target-language/main.tsx`）。
- 新增 `web/src/target-language/`：
  ```
  main.tsx            # 入口
  TargetLanguagePage.tsx
  ```
- `src/everlingo/gateway/web_acceptor.py` 静态页 fallback（早于 catch-all `/{path:path}`）：
  ```
  GET /console/me/target-language  →  web/dist/target-language.html
  ```
- **Me 页导航**：`web/src/me/MePage.tsx` 的 `entries` 列表首项新增「目标学习语言」入口（`lucide-react` 的 `Languages` 图标）→ `/console/me/target-language`。

### 页面元素

`TargetLanguagePage.tsx` 加载时并发请求 `GET /api/user-profile/status` 与 `GET /api/target-language/list`。

**「支持的目标学习语言」列表**（单列为一行，点击即选中，不立即保存）：

| 目标学习语言 | 默认 | 笔记库状态 |
|---|---|---|
| English | Yes | 已初始化 |
| 日本語 | No | 未初始化 |
| Français | No | 未初始化 |
| 简体中文 | No | 已初始化 |
| Deutsch | No | 未初始化 |

- **选中态**：行首圆点单选标识（选中 `border-primary bg-primary`）。
- **笔记库状态**：`已初始化` / `未初始化` / `未知（indexer 不可达）`。
- **禁用行**：`vault_initialized=null`（未知）的行 `disabled`，不允许选中（避免在 indexer 离线时静默 `create_vault` 失败）。
- **「保存」按钮**：
  - 禁用条件：未选中 / 选中语言 `vault_initialized=null` / 保存中。
  - **永远 Enable 语义**：不要求 `selected !== current_default`——即使选中的就是当前默认语言，只要其 vault 未初始化，也可点击以触发补初始化。
  - 点击 → `POST /api/target-language/default`，无确认弹窗（未初始化时由后端静默初始化）。
  - 成功后显示「已切换，对话已重置」，约 800ms 后 `window.location.href = '/'` 回到聊天首页（chat session 是内存态，整页跳转即重置对话上下文）。

### 引导模式（首次使用）

页面加载后若 `status.needs_setup=true`（§「有效的默认目标学习语言配置」不满足），进入**引导模式**：

- 顶部固定提示条：「请选定一个有效的目标学习语言并初始化笔记库」。
- 保存按钮在未选中 / 选中语言 `vault_initialized=null` / 保存中时禁用；选中语言已初始化或未初始化但可静默初始化时均可点击（含「当前默认但未建」场景，点击即触发 `create_vault` 补初始化）。
- **不提供**「返回聊天」的捷径（底部「返回聊天」按钮隐藏），避免用户绕过配置。

### 页面加载状态

- `loading`：居中 `Loader2` spinner。
- `error`：显示「无法加载语言列表」。
- `ready`：渲染语言列表。

## Chatbot 首页强制跳转

`web/src/main.tsx`（chatbot SPA）改为 **async bootstrap**：

1. 先 `fetch /api/user-profile/status`（渲染 loading 占位，不先挂载 `ChatWindow`，避免 chatbot UI 闪现）。
2. 若 `needs_setup=true` → `window.location.href = '/console/me/target-language'`，不渲染聊天 UI。
3. 否则正常渲染 `<ChatWindow />`。
4. fetch 失败（如 indexer 不可达导致 5xx）→ 放行进入 chatbot（不因健康检查失败而阻断聊天）。

策略为**持续强制 redirect 直至修复**：只要 default 无效或 vault 未建，每次进首页都会跳走，确保用户不会在未配置状态下进入 chatbot 触发各种隐式错误。

## 副作用联动

切换默认目标学习语言成功后：

- Chat Agent 检测到 `profile.language.target_language` 变化，按 `src/everlingo/agents/agent.py` `_refresh_agent_if_needed` 既有逻辑（`target_lang` 变化 → 关闭旧 MCP stream → 重建 agent）重建；MCP stream 重开。
- 即当前对话上下文会**重置**。前端在保存成功后提示「已切换，对话已重置」并整页跳转（清空内存态 chat session）。

## 相关文档

| 文档 | 内容 |
|---|---|
| [ADR 20260801](/docs/ADR/20260801-user-onboarding.md) | 决策依据：页面设计、API 契约、实施顺序 |
| [ws-console.md](/docs/impl-spec/workspace-console/ws-console.md) | 页面导航图（Me 节点下「目标学习语言」分支） |
| [ws-console-arch.md](/docs/impl-spec/workspace-console/ws-console-arch.md) | 架构设计：API 端点表 §5.2、静态页 fallback §5.3、构建入口 §6.1 |
| [DOMAIN.md](/DOMAIN.md) | 领域术语：「笔记库已初始化」「有效的默认目标学习语言配置」 |
| [vault-mcp-spec.md](/docs/impl-spec/vault-mcp/vault-mcp-spec.md) | `list_vaults` / `create_vault` MCP 工具契约 |
