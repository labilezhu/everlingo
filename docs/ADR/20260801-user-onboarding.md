# ADR: 用户首次使用引导与目标学习语言设置页

- 状态：Accepted
- 日期：2026-08-01
- 决策参与方：用户、opencode
- 相关文档：
  - [领域模型](../../DOMAIN.md)
  - [Workspace Console 架构](../impl-spec/workspace-console/ws-console-arch.md)
  - [Workspace Console 总览](../impl-spec/workspace-console/ws-console.md)
  - [Vault MCP Spec](../impl-spec/vault-mcp/vault-mcp-spec.md)
  - [Web Chatbot](../impl-spec/web-chatbot.md)
  - [Chat Agent Spec](../impl-spec/chat-agent-spec.md)

---

## 1. 动机

产品面向个人本地部署，新用户首次使用时需要完成两件事才能正常学习：

1. 选定一个**默认目标学习语言**（`target_language`），写入 `$workspace/everlingo.yaml` 的 `user_profile.language.target_language`。
2. 为该语言**初始化笔记库（vault）**，否则 Chat Agent 的 `session.configure(lang=...)` 虽能自动 create_vault，但用户在开始学习前最好明确这一副作用。

现状下，这两件事只能通过手改 yaml + 手跑工具完成，对非技术用户不友好。本 ADR 决定：

- 在 Workspace Console 前端新增一个**目标学习语言设置页**，提供可视化列表 + 保存。
- 在用户登录后访问 Web Chatbot 首页时，**强制检查**默认目标学习语言是否「有效且已初始化」，否则自动跳转到设置页进行首次引导。

## 2. 关联的规则变更

本 ADR 同时决定一项**领域规则变更**：

> **`target_language` 与 `interface_language` 不再要求互斥，二者可以相同。**

原约束见 `DOMAIN.md` 第 39/40/53 行、`models.py:UserProfile.validate()`、`everlingo.example.yaml:38`、`tests/test_setting.py:55`。解除该约束的理由：

- 用户可能希望界面语言与学习语言一致（例如以英语学英语的进阶用户）。
- 强行互斥会让用户在「想学的语言恰好等于界面语言」时无路可走，需要额外设置 `interface_language` 入口，增加复杂度。
- 互斥并非业务必需：`agent.py` 的 prompt 逻辑（第 239 行附近）已经独立处理 `dest_lang != src_lang` 的兜底，不依赖两者相异。

**前置变更清单**（实现设置页前必须先完成）：

| 文件 | 变更 |
|---|---|
| `DOMAIN.md` | 删除「不能与 target_language 相同」「不能与 interface_language 相同」「两者不能相同」三处约束 |
| `src/everlingo/models.py` | `UserLanguage.target_language` description 去掉「不能与 interface_language 相同」；`UserProfile.validate()` 删除「两者相同」错误分支 |
| `everlingo.example.yaml` | 注释去掉「不能与 interface_language 相同」 |
| `tests/test_setting.py` | 删除/改写 `test_*_same_language*` 断言「不能相同」的用例 |
| `src/everlingo/agents/agent.py` | 复核 prompt 文案（第 239 行附近）确认在两者相同时仍能正确推理 `dest_lang`，必要时调整文案 |

## 3. 概念定义

- **支持的目标学习语言**：固定 5 种 `en / ja / zh-CN / fr / de`（即 `LANGUAGES` 字典的 key）。这是产品的固定能力，不可由用户增删。
- **默认目标学习语言**：`user_profile.language.target_language` 的取值，最多一个。
- **笔记库已初始化**：该 lang 出现在 Vault MCP `list_vaults` 工具的返回结果中（即 `$workspace/memory/languages/$lang/` 存在并已注册到 indexer）。
- **有效的默认目标学习语言配置**：满足以下全部条件
  1. `target_language` 非空
  2. 取值属于「支持的目标学习语言」5 种之一
  3. 该 lang 的笔记库已初始化

  注意：条件中**不再**包含「≠ interface_language」。

## 4. 目标学习语言设置页

### 4.1 页面归属与 URL

挂在 **Me 页**之下作为直接子页，URL `/console/me/target-language`。理由：目标学习语言是**用户偏好**而非 channel 运维，归 Me 页比归 Workspace Console 的 channels admin 更贴切。

`ws-console-arch.md §5.3` 静态页 fallback 表与 `§6.1` vite `rollupOptions.input` 增加对应入口；`ws-console.md` §页面导航图相应扩展 `Me` 节点下增加一条「目标学习语言」分支。

### 4.2 页面元素

**「支持的目标学习语言」列表**：列出全部 5 种语言及其当前状态。

| 目标学习语言 | 默认 | 笔记库状态 |
|---|---|---|
| English | Yes | 已初始化 |
| 日本語 | No | 未初始化 |
| Français | No | 未初始化 |
| 简体中文 | No | 未初始化 |
| Deutsch | No | 未初始化 |

- `默认` 列：是否为当前 `target_language`。单选，切换即选中（不立即保存）。
- `笔记库状态` 列：取自 `list_vaults`。
  - `已初始化` / `未初始化` / `未知`（indexer 不可达时）。
  - `未知` 行不允许被选为默认（避免在 indexer 离线时静默 create_vault 失败）。

**「保存」按钮**：将选中语言写回 `everlingo.yaml`。保存时若选中语言未初始化，后端**静默**调用 Vault MCP `create_vault` 完成初始化后再写 yaml。无确认弹窗。

### 4.3 首次使用引导

设置页加载时，若判断 `默认目标学习语言` 配置**无效**（按 §3 定义），自动进入「引导模式」：

- 顶部固定提示条：「请选定一个有效的目标学习语言并初始化笔记库」。
- 保存按钮在选中语言且（已初始化或可静默初始化）前禁用。
- 引导模式下不提供「返回 chatbot」的捷径，避免用户绕过配置。

## 5. Web Chatbot 首页强制跳转

### 5.1 状态端点

新增后端端点：

```
GET /api/user-profile/status
→ {
    target_language: str,           # 当前取值，空字符串表示未设置
    is_valid: bool,                 # §3 三条件全满足
    vault_initialized: bool|null,   # list_vaults 结果；indexer 不可达时 null
    needs_setup: bool               # = !is_valid
  }
```

- 该端点**不依赖认证**，单用户本地拓扑（无 login）同样可访问，使首次引导在两种拓扑下都生效。
- `vault_initialized` 字段语义同设置页列表的「笔记库状态」：`list_vaults` 不可达时为 `null`，此时 `is_valid=false`、`needs_setup=true`。

### 5.2 chatbot 首页逻辑

`web/src/`（chatbot SPA）加载时：

1. 先 `fetch /api/user-profile/status`。
2. 若 `needs_setup=true`：`window.location.href = '/console/me/target-language'`，不渲染聊天 UI。
3. 否则正常进入 chatbot。

策略为**持续强制 redirect 直至修复**：只要 default 无效或 vault 未建，每次进首页都会跳走。这是有意为之，确保用户不会在未配置状态下进入 chatbot 触发各种隐式错误。

### 5.3 设置页同样消费该端点

设置页加载时调用同一 `GET /api/user-profile/status`，`needs_setup=true` 即进入引导模式。单一真源，避免 chatbot 与设置页对「是否需要引导」判断漂移。

## 6. API 契约

补入 `ws-console-arch.md §5.2`：

```
GET  /api/target-language/list
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

POST /api/target-language/default
  body: { lang: "ja" }
  → 服务端依次：
     1. 校验 lang ∈ 5 种支持语言，否则 400
     2. 调 list_vaults 查 lang 是否已建：
        - 已建 → 直接写 yaml
        - 未建 → 静默调 create_vault(lang) → 成功后写 yaml
        - list_vaults/create_vault 不可达 → 503，不写 yaml
     3. 写 user_profile.language.target_language 到 $workspace/everlingo.yaml
  → 返回 200 + 新 list（同 GET /api/target-language/list 结构）
```

复用 `vault_editor_api.py` 既有 MCP client session 模式（`session.call_tool("list_vaults")` / `create_vault`）。

## 7. 副作用联动

切换默认目标学习语言成功后：

- Chat Agent 检测到 `profile.language.target_language` 变化，按 `agent.py:705` 既有逻辑重建 agent；MCP stream 按 `chat-agent-spec.md:118` 重开。
- 即当前对话上下文会**重置**。前端在保存成功后提示「已切换，对话已重置」，并清理本地消息状态。

## 8. 文档准确性纠正

设计讨论中曾表述为「`$workspace/everlingo.yaml` 中的 `target_language`」，实际字段路径为 `user_profile.language.target_language`。本 ADR 与后续实现文档统一使用准确路径。

## 9. 不在本范围

- **`interface_language` 的可视化设置**：本 ADR 不引入界面语言设置入口。`interface_language` 仍由 yaml / 部署模板配置。未来如需，再另起 ADR。
  > **已于 Phase 3 解除**：见 [ADR 20260806-phase3-web-i18n-onboarding.md](20260806-phase3-web-i18n-onboarding.md) —— 引入 onboarding step 1（`/console/me/interface-language`）与 Me 页切换 UI，新增 `POST /api/user-profile/interface-language` 写入端点。
- **多用户共享 workspace 的 target_language 隔离**：`target_language` 是 workspace 级配置，多用户共享一 workspace 时互相可见且互相影响。这是既有限制，本 ADR 不解决。
- **indexer 离线时的 vault 创建重试 UI**：仅显示「未知」并禁用选中，不做自动重试。

## 10. 实施顺序

1. 前置变更（§2 清单）：解除 interface/target 互斥约束，改测试与文档。 （已完成）
2. 后端：新增 `GET /api/user-profile/status`、`GET /api/target-language/list`、`POST /api/target-language/default` 三个端点（复用 MCP client）。
3. 后端单测：端点行为 + indexer 不可达降级 + create_vault 静默调用。
4. 前端：vite 入口 + `/console/me/target-language` 页面 + Me 页导航链接。
5. 前端：chatbot 首页 fetch status + redirect 逻辑。
6. 文档：更新 `ws-console-arch.md`（§5.2/§5.3/§6.1）、`ws-console.md`（导航图）、`DOMAIN.md`（§2 已在步骤 1 改）。
7. 更新 `TASKS.md` 记录完成项。
