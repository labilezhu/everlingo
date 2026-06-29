# Current Sprint

## 进行中的任务

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"
 - 2026-06-29 21:49 | 重构 Memory Extract Agent system prompt：将「输出 schema / 字段说明与真实性约束 / 输出格式」三段抽离至 `src/everlingo/mem/agents/mem_extract_spec.md`，改用 `md_prompt_compiler` 的 `PackageSource` + `compile_prompt` 加载，与 Memory Writer Agent 加载 `vault_spec.md` 机制一致；同步更新设计文档 `docs/impl-spec/memory-extract-agent-spec.md` System prompt 要点 / Prompt 文件加载 一节
