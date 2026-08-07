# ADR: Agent 输入/输出契约 spec 迁为代码资产（移出 vault 模板）

- 状态：Accepted
- 日期：2026-08-08
- 决策参与方：用户、opencode
- 相关文档：
  - [ADR 20260808-vault-template-i18n.md](20260808-vault-template-i18n.md)（**部分修订**，见 §6）
  - [Memory Writer Agent Spec](../impl-spec/memory-writer-agent-spec.md)
  - [Chat Agent Spec](../impl-spec/chat-agent-spec.md)
  - [Vault MCP Spec](../impl-spec/vault-mcp/vault-mcp-spec.md)

---

## 1. 动机

`vault/templates/default/{zh-CN,en}/spec/` 下的 `spec/*.md` 存在两类性质不同的文件：

- **用户 vault 内容规范**（用户写笔记时遵循，可定制）：`vault_spec.md`、`kb_items_spec_*.md`、`events_spec.md`、`index.md`。
- **Agent I/O 契约**（纯系统数据结构，用户既不读也不该改）：`envelope_spec.md`（输入消息信封 schema）、`mem_entry_spec.md`（MemoryEntry 参数 schema）、`memory_extract_output_spec.md`（抽取输出规范）。

后三者是 agent 的输入/输出契约：由 LLM / 前端代码消费，用户不会去定义。把它们放在 `vault/templates`（语义上是「用户可定制的 vault 初始化模板」）既误导用户以为可改，又让 agent 在运行时依赖「vault 在线才拿得到 schema」——vault 离线时这些契约也随之不可用。

## 2. 决策

| # | 决策点 | 选择 |
|---|---|---|
| 1 | 迁移目标 | 3 个契约 spec 移到 `src/everlingo/agents/spec/`（agent 代码资产，与 `agent.py` 同级） |
| 2 | 语言 | **只保留 zh-CN 版本**。作为 agent 内部契约由 LLM 消费（LLM 跨语言能力足够），维护 en/zh 双语翻译无必要，故删除 en 版 |
| 3 | 加载方式 | 用 `PackageSource(package="everlingo.agents.spec")` + `compile_prompt` 本地编译加载，不再经 MCP 从 vault 加载 |
| 4 | Chat Agent 注入 | `memory_extract_output_spec`（含 include 的 `mem_entry_spec`）编译后 `shift_headings(+2)` 注入 Chat Agent system prompt「抽取对话内容到笔记」节；`envelope_spec` 同法注入「结构化用户输入（envelope）」节 |
| 5 | Memory Writer | `mem_entry_spec` / `envelope_spec` 本地加载；`vault_spec` 仍是用户 vault 内容，保持经 MCP 从 vault 加载 |
| 6 | 模板 | `templates/default/{zh-CN,en}/spec/` 不再 seed 这 3 个文件（`create_vault`/`reset_vault` 遍历模板包，自动不含它们，无需特殊处理） |

## 3. 设计要点

### 3.1 迁移后加载

```python
_spec_source = PackageSource(package="everlingo.agents.spec")
envelope_spec = compile_prompt("envelope_spec.md", _spec_source)
memory_extract_output_spec = compile_prompt("memory_extract_output_spec.md", _spec_source)
```

与吞掉 Chromium/TypeScript 无关；这是纯 Python 包资源，`importlib.resources.files` 对无 `__init__.py` 的命名空间子包（`everlingo.agents.spec`）与现有 `templates.default.zh-CN.spec` 行为一致。

### 3.2 vault 离线强健性

迁移前 Chat Agent 在 vault 离线时 `envelope_spec_content` 取 `None`（脆弱兜底）。现在是代码资产，始终可用，兜底分支删除，system prompt 更稳定。

### 3.3 include 链

`memory_extract_output_spec.md` include `./mem_entry_spec.md`，两者同包移动，`PackageSource` 相对路径解析不变。`mem_entry_spec.md` 中对 `vault_spec.md`（留在模板）的引用是普通 markdown 链接（非 include），不参与编译链，仅作为软引用文本（Memory Writer 已单独注入 vault_spec 内容）。

## 4. 备选方案（未采纳）

- **保留运行时按需加载（vault_mcp_read）**：`memory_extract_output_spec` 原由 LLM 在抽取前主动 `vault_mcp_read(path="spec/memory_extract_output_spec.md")`。改为注入 system prompt，消除「LLM 必须记得先 read» 的脆弱性，且文件很小（11 行 + include）。
- **保留 en/zh-CN 双版本并按界面语言选**：与 ADR 20260808 的 i18n 方向一致，但这 3 个是 agent 内部契约（用户不可见），双语维护成本大于收益，不采纳——这正是 §6 修订 ADR 20260808 的原因。

## 5. 影响

- 源码：`src/everlingo/agents/agent.py`、`src/everlingo/mem/agents/mem_writer_agent.py`、`src/everlingo/tools/request_memory_extract.py`。
- 新增：`src/everlingo/agents/spec/{envelope_spec,mem_entry_spec,memory_extract_output_spec}.md`（zh-CN）。
- 删除：`templates/default/{zh-CN,en}/spec/` 下对应 3 个文件（共 6 个）。
- 测试：`tests/test_mem_writer_agent.py` / `tests/test_unified_agent.py` fixture 包路径改 `everlingo.agents.spec`；`tests/test_mem_vault_mcp_server.py` 删 3 个文件的 seed/覆盖断言。
- 文档：memory-writer-agent-spec.md、chat-agent-spec.md、envelope-impl-spec.md、chat-agent-tools-spec.md、i18n.md、TASKS.md、release notes。

## 6. 对 ADR 20260808-vault-template-i18n.md 的修订

ADR 20260808 为 `spec/*.md`（含这 3 个文件）建了 en 版以服务英文界面。本 ADR 界定 `envelope_spec` / `mem_entry_spec` / `memory_extract_output_spec` 为 **agent 内部契约而非用户界面内容**：用户不阅读它们（envelope 由前端代码构造、entry/extract 由 LLM 消费），因此不随界面语言本地化、仅保留 zh-CN，并从 `vault/templates` 迁出。ADR 20260808 中关于 `vault_spec.md` / `kb_items_spec_*.md` / `events_spec.md` / `index.md` 的 en/zh 拆分与按界面语言选择逻辑**保持不变**。
