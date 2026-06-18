# Current Sprint

## 计划中的任务

## 可执行的任务

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"
### Agent 重构：Gateway / Session / Agent / Channel 抽象

- **新增** `src/everlingo/gateway/channels/stdio_channel.py`：实现 `StdioChannel`，`recv` 阻塞读取 stdin，支持 `/quit` 退出和 EOF/KeyboardInterrupt；`send` 输出到 stdout。
- **重构** `src/everlingo/agents/agent.py`：将 `_build_system_prompt` 和 Agent 构建逻辑从原 `chat.py` 迁入 `MainAgent`；修复 `invoke` 中 `messages` 变量名 bug（`self._messages` vs 局部变量）。
- **实现** `src/everlingo/gateway/session.py`：`Session.run()` 完整消息循环——`channel.init()` → 循环 `channel.recv()` → `agent.invoke()` → `channel.send()`，收到 `None` 时退出。
- **实现** `src/everlingo/gateway/gateway.py`：`argparse` 支持 `--channel_stdio` / `--channel_wechat`（wechat 暂未实现）；迁入 profile 初始化向导（`_ensure_profile`、`_run_profile_setup`）；`_run_stdio()` 组装并启动 Session。
- **调整** `src/everlingo/main.py`：改为调用 `gateway._run_stdio()`，与 `gateway --channel_stdio` 等效。
- **删除** `src/everlingo/chat.py`：原有逻辑已全部迁移至 gateway/agents 层。
- **新增** `tests/test_gateway.py`：10 个单元测试覆盖 `StdioChannel`（recv 正常/quit/EOF/KeyboardInterrupt）和 `Session.run()`（消息循环、回复发回 channel）。
- **修复** `tests/test_unified_agent.py`：将 `from everlingo.chat import _build_system_prompt` 改为 `from everlingo.agents.agent import _build_system_prompt`。
