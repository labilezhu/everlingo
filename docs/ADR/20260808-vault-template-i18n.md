# ADR: Vault 目录初始化模板 i18n（按界面语言拆分模板）

- 状态：Accepted
- 日期：2026-08-08
- 决策参与方：用户、opencode
- 相关文档：
  - [i18n 整体设计](../i18n/i18n.md) §Phase 6
  - [Vault MCP Spec](../impl-spec/vault-mcp/vault-mcp-spec.md)
  - [ADR 20260806-interface-language-optional.md](20260806-interface-language-optional.md)（Phase 1，`resolve_interface_language` / `AVAILABLE_INTERFACE_LANGUAGES`）
  - [Chrome/移动端/MCP 使用界面语言](../i18n/i18n.md) §interface_language 配置语义

---

## 1. 动机

### 1.1 现状

`create_vault` / `reset_vault` / `session.configure` 用 `src/everlingo/mem/vault/templates/default/*` 对 `$workspace/memory/languages/$lang/vault/` 做初始化，模板内容**硬编码中文**（spec/*.md 与 items/**/index.md 均为中文）。

### 1.2 问题

模板里的 spec 规范、目录 index 标题给语言学习者阅读，其「主要语言」按 vault_spec.md 规定是 `界面语言`（interface language）。英文界面用户在创建新目标学习语言 vault 时，得到的 spec 规范和笔记目录标题仍是中文，与界面语言不一致，也影响以英文为主语言的 LLM 正确遵循规范。

### 1.3 现有约束 / 已建立机制

- 界面语言 `interface_language` 与目标学习语言 `lang` 是两套独立集合（Phase 1）。
- `AVAILABLE_INTERFACE_LANGUAGES = ("zh-CN", "en")`，`resolve_interface_language()`（精确命中 → OS locale 归一化 → 前缀兜底 → en）已在运行时推断界面语言。
- MCP server 进程（indexer 内嵌）不持有任何 user profile（多用户 ws-router 拓扑下 indexer 是 workspace 级共享），因此模板语言的选择**不能**在 server 内直接读 profile，必须由调用方（agent / gateway）显式传入。

## 2. 决策

| # | 决策点 | 选择 |
|---|---|---|
| 1 | 模板组织 | `templates/default/` 下按界面语言拆分子包 `en/`、`zh-CN/`（保留 `default` 这层，便于未来扩展其它模板族） |
| 2 | 模板语言选择 | 运行时按 `interface_language` 匹配，逻辑复用 `resolve_interface_language()`（精确命中 → OS locale → 前缀 → 兜底 en），并加「模板子包存在性」检查，缺失则回退 `en` |
| 3 | `create_vault` / `reset_vault` 参数 | 新增可选 `interface_language: str \| None = None`；省略时在 server 内推断（OS locale 容错），回退 en |
| 4 | `session.configure` | 已有 `interface_language` 参数；自动创建缺失 vault 时透传给 `create_vault` |
| 5 | 调用链 | 后端各调用方显式传 `interface_language`（profile resolved 值或 entry.interface_language） |
| 6 | 存量受影响性 | 既有已初始化 vault 不受影响（create_vault 幂等不覆盖）；reset_vault 用当前界面语言重 seed |
| 7 | 测试 | 模板双层文件树一致性 + 各语言实例化内容断言 + 推断/回退/透传 |

## 3. 设计要点

### 3.1 模板目录拆分

将原 `templates/default/*`（中文）原样移至 `templates/default/zh-CN/`，并把内容翻译成英文放在 `templates/default/en/`。两份模板的**相对路径树保持一致**（新增测试断言），保证「按语言选整棵模板」成立。

```text
templates/default/
  en/
    index.md
    spec/*.md
    items/**/index.md
    events/index.md
  zh-CN/
    index.md
    spec/*.md
    items/**/index.md
    events/index.md
```

### 3.2 server 端模板语言解析

新增 helper `_resolve_template_lang(interface_language) -> str`：

1. `resolve_interface_language(interface_language or "")` 取候选 `tpl_lang`（精确命中 / OS locale 推断 / 前缀兜底 / `en`）。
2. 校验 `importlib.resources.files("...templates.default.{tpl_lang}")` 为目录；否则回退 `"en"`（`en` 视为恒存在）。

`create_vault` / `reset_vault` 的 `PackageSource` 与 `root_traversable` 均按 `tpl_lang` 拼接子包路径。

- 2026-08-08 修订：`envelope_spec.md`、`mem_entry_spec.md`、`memory_extract_output_spec.md` 界定为 agent 输入/输出契约，迁出 `vault/templates`（见 [ADR 20260808-agent-specs-relocate.md](20260808-agent-specs-relocate.md)），不再参与 en/zh 拆分；本 ADR 关于 `vault_spec.md` / `kb_items_spec_*.md` / `events_spec.md` / `index.md` 的拆分逻辑不变。

### 3.3 spec/*.md 的 include 展开

`spec/*.md`（无 frontmatter，不含已迁出的 3 个 agent 契约）走 `compile_prompt + PackageSource`，PackageSource 指向所选语言子包，include 相对路径在语言子包内解析（如 `vault_spec.md` 内联子规范引用）。`spec/index.md` 与 items 目录 index 有 frontmatter，raw copy。

### 3.4 调用链界面语言来源

| 调用方 | interface_language 来源 |
|---|---|
| `session.configure` | 显式参数（已有） |
| Memory Writer `mcp_vault_connection(entry.lang)` | `entry.interface_language`（由 Chat Agent 从 profile 填充） |
| Chat Agent `mcp_vault_connection(_target_lang)` | `self._interface_lang` |
| Vault Editor `_configured(lang)` | 省略时 `load_resolved_profile()` 兜底 |
| `POST /api/target-language/default` | `load_resolved_profile()`（create_vault） |
| `POST /api/target-language/reset-vault` | `load_resolved_profile()`（reset_vault） |

## 4. 备选方案（未采纳）

- **服务端内读 profile 选语言**：MCP server 不持有 user profile（多用户拓扑 workspace 级共享），不可行。
- **去掉 `default` 这层，直接 `templates/{en,zh-CN}`**：失去未来扩展其它模板族的扩展点，且与既有 `_VAULT_TEMPLATES_PACKAGE` 语义（`default` 是模板族根）不连贯，未采纳。
- **模板内容按「目标学习语言」而非「界面语言」拆分**：spec 规范语言按 vault_spec.md 应跟随界面语言，方向错误，未采纳。

## 5. 影响

- 源码：`src/everlingo/mem/vault/mcp_server/mcp_server.py`（`_resolve_template_lang` + 两工具签名 + configure 透传）、`src/everlingo/mem/agents/mem_writer_mcp_client.py` / `mem_writer_agent.py`、`src/everlingo/gateway/vault_editor_mcp_client.py` / `vault_editor_api.py`、`src/everlingo/gateway/user_profile_api.py`。
- 模板：`templates/default/` 拆分为 `en/`、`zh-CN/` 两套。
- 测试：`tests/test_mem_vault_mcp_server.py` 新增 i18n 模板选择用例。
- 文档：i18n.md Phase 6、vault-mcp-spec.md、vault-mcp-spec-tools.yaml、TASKS.md、release notes。