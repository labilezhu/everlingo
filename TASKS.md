# Tasks

## 计划的任务

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"

- 2026-07-31 | **Workspace Console — P1（wechat gateway 进程内 admin server）**：新增 `src/everlingo/gateway/wechat_admin/`（state.py 线程安全状态机 `WechatAdminState`；lifecycle.py flock 单例锁 + pid 文件；server.py UDS FastAPI `/status` `/last_error` `/shutdown` + `AdminServer` 可优雅关闭）。改造 `wechat_channel.py`：注入 SDK 回调更新状态、启动路径由 `bot.run()` 改为 `_run_thread()`（显式 loop + main task，便于跨线程取消），`_wrap_login()` monkey-patch `bot.login` 注入 `logined`（覆盖首登与 session-expired 重登）、`request_stop()`（stop + 主协程 cancel，解决 QR 等待/长轮询阶段 stop() 不生效）。改造 `session_acceptor.py`：`WechatSessionAcceptor.start` 获取锁 + 写 pid + 并行起 admin server，`_run_until_bot_done` 按「bot 结束 / uvicorn 信号退出」两路径收尾退出进程。`gateway.py` 捕获 `LockAcquireError` 优雅退出。文档 `docs/impl-spec/workspace-console/`（README/architecture/phased-impl）。测试：wechat_admin 22 项 + wechat_channel 新增 8 项，相关 97 测试通过。手工验证：/status（waiting_scan + 真实 QR URL）、/shutdown（2s 退出 + pid 清理）、SIGINT（2s 退出 + pid 清理）、SIGTERM（退出；pid 因 uvicorn 重抛原信号硬终止而残留，web 侧 P2 用 pid 存活校验兜底）、SIGKILL 崩溃后重启（stale socket 被 unlink、锁自动释放）、双实例锁互斥。
- 2026-07-31 | **Python base image 迁移 bookworm → trixie**：`python:3.12.13-bookworm` → `python:3.12-trixie`。改动：`deploy/deps-base/Dockerfile`（deps/runtime 两 stage base）、`deploy/ws-container/ws-container-spec.md`（3 处 base 描述）、`docs/impl-spec/multiple-users/deploy.md`（ws-router/ws-master 示例 Dockerfile 片段 4 处）。副作用说明——trixie（Debian 13）系统 SQLite 为 3.46.1（bookworm 为 3.40.1），`LIMIT ?` 已支持传给 vec0 xBestIndex；`store.py:_vec0_knn` 仍用 `k = ?`（sqlite-vec 官方推荐写法，两端兼容），仅同步更新 store.py 与 memory-vault-embedding-spec.md 中的注释措辞。ws-container/ws-router/ws-master 三 Dockerfile 均经 `ARG DEPS_IMAGE` 继承，无需改。需重新构建并推送 deps-base 镜像（`everlingo-deps`）到 ghcr 后下游镜像生效。
