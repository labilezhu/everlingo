# Current Sprint

## 进行中的任务


## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"

- 2026-07-06 | 给 Vault MCP Server 新增两个 workspace 级 vault 管理工具（`list_vaults` / `create_vault`），补齐 agent 「发现/创建 lang」能力缺口，并让 indexer 排除 `VALUT_SPEC.md` 不入索引：
  - `list_vaults` — 列出 `$workspace/memory/languages/` 下已建立 `vault/` 子目录的 lang 代码，复用 `workspace.lang_dirs()`，无需 session.configure。返回 `{vaults: [str], count: int}`。
  - `create_vault` — 校验 lang 名 → mkdir `$lang/vault/` → 幂等写 `$lang/vault/VALUT_SPEC.md`（内容由 `compile_prompt("vault_spec.md", PackageSource(package="everlingo.mem.vault"))` 合成，**不** shift_headings，因为是独立顶级文档）→ 同步调 `state._open_lang(lang)` 注册到 indexer（与 `LangDiscoveryWatcher` 同一入口，加锁幂等）。返回 `{ok, lang, vault_path, created, spec_written, registered}`，`vault_path` 为相对 workspace 根的路径。
  - 两者均为 workspace 级工具，**豁免** session.configure（不绑特定 lang，workspace 还没有任何 lang 时也得能创建第一个）。
  - indexer 端新增 `is_excluded_vault_file(abs_path, memory_root)` helper（`src/everlingo/mem/vault/search/indexer.py`），统一排除 `tmp/` 子目录与 `VALUT_SPEC.md`，调用方为 `walk_vault` / `sync.reconcile` / `watcher._dispatch`。
  - 改动：`src/everlingo/mem/vault/mcp_server/mcp_server.py` 新增两个工具 + 更新 `_SERVER_INSTRUCTIONS`（12→14、典型用法序列更新、新增 vault 管理分组与豁免说明）；`src/everlingo/mem/vault/search/indexer.py` 新增 helper + 更新 `walk_vault`；`src/everlingo/mem/vault/search/sync.py` reconcile 改用 helper；`src/everlingo/mem/vault/search/watcher.py` `_dispatch` upsert 分支调 helper；`docs/impl-spec/vault-mcp/valut-mcp-spec-tools.yaml` 新增两个工具的 inputSchema/outputSchema（放在 session.configure 之前）；`docs/impl-spec/vault-mcp/valut-mcp-spec.md` 「会话 lang 机制」节加 vault 管理工具豁免小节、Server Instructions 契约 8 项中工具分组/工作流两项同步更新、「实现细节」节新增「vault 管理工具实现绑定」子节。
- 2026-07-06 | 修复 Memory Extract Agent 抽取不到"用户明确要求记住"内容的根因：Chat Agent 原本被 prompt 指示"用户要求记住时只回『已提交笔记请求』"，导致 new_messages 中无该知识点的实际内容，Extract Agent 既无事实来源又受 mean_summary 真实性约束，要么不抽、要么自造。改为：Chat Agent 必须先在本轮回复中产出该知识点的释义/解释（用 dest_lang），再附"已提交笔记请求"。改动：`src/everlingo/agents/agent.py` `_build_system_prompt()` 记忆写入段、`docs/impl-spec/chat-agent-spec.md`「Memory Extract」节新增「用户要求记住某知识点时的行为契约」小节、`tests/test_unified_agent.py` 新增 `test_system_prompt_instructs_produce_content_before_ack` 验证 prompt 包含"先产出释义再附提示"约束与行序。Memory Extract Agent 代码 / spec / 输出 spec 未改。
- 2026-07-06 | 给 Vault MCP Server 增加 server-level `instructions`（通过 MCP `initialize` 响应 `instructions` 字段暴露给 agent 阅读的"服务器自述"），覆盖：服务器定位、12 工具分组、必须先 `session.configure` 的强约束工作流、path 相对 lang vault 根、`mode=hybrid` 默认与 lang 跨覆盖、watcher 自动索引副作用、stream 级会话生命周期、典型用法序列。改动：`src/everlingo/mem/vault/mcp_server/mcp_server.py` 新增模块级常量 `_SERVER_INSTRUCTIONS` 并在 `create_mcp_app` 中传给 `FastMCP(name=..., instructions=...)`；`docs/impl-spec/vault-mcp/valut-mcp-spec.md` 新增 `## Server Instructions` 节，记录 FastMCP 绑定方式 + 8 条最小契约清单（实现方可调整措辞但必须覆盖全部 8 项）；`tests/test_mem_vault_mcp_server.py` 新增 `test_initialize_exposes_instructions` 断言 `initialize.instructions` 非空且含 `session.configure` / `hybrid` / `vault` / `watcher` 关键词。9 项测试全过。



