
# Agent Instructions

## Test / lint

- Tests: `uv run pytest tests/<file>::<name> -v` (单文件 / 单用例) 或 `uv run pytest tests/` (全量)。
- 项目**未**配置 ruff / mypy / black；纯 Python + pytest 即可。变更源码后跑相关单测即可，无需跑全量。
- venv 路径：`.venv/`，由 `uv` 自动管理；如缺失 `uv sync`。

Before making changes, make sure read following documentations:

文档说明：
- [产品文档](./PRODUCT-FUNC.md)
- [领域模型](./DOMAIN.md)
- [架构设计](./ARCHITECTURE.md)
- [ROADMAP](ROADMAP.md)
- [项目状态](./STATE.md)
- [当前开发任务](./TASKS.md)
- [代码风格](/CODING_STYLE.md)
- [测试风格](/TEST_STYLE.md)

## Rules

- Generally speaking, when generate code, write tests
- Never add dependencies without approval
- 如发现文档说明十分模糊或矛盾的，询问确认后再执行
- Explain your design of implmentation and let user comfirm the design before take action.
- 如果实现和设计文档不同，询问用户是否需要更新设计文档
- 如果实现了设计文档未提到的重要内容，询问用户是否需要更新设计文档
- If you change any source code, ALWAYS update [TASKS.md](/TASKS.md) to record what you have done

Output:
- Explain your design
- Then generate code


## Boundaries
- 🚫 **Never do:** commit secrets


