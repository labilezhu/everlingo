# Current Sprint

## 进行中的任务

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"
- 2026-06-28 | Memory Extract Agent 改用独立 LLM 工厂 `create_extract_llm()`，temperature=0 以保证抽取任务的结构化输出确定性。改动：`src/everlingo/llm.py` 新增 `create_extract_llm()`（同 model/callbacks/tracing，仅 temperature=0）；`src/everlingo/mem/agents/mem_extract_agent.py` 切换 import 与调用；`docs/impl-spec/memory-extract-agent-spec.md` 同步更新「已知简化 / 待评估」段落标注已实施独立配置。`create_llm()` 保持 temperature=0.7 不变，主对话语气不受影响。
