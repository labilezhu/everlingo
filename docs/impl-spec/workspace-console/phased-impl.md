# Workspace Console — 分阶段实施计划

按依赖顺序分阶段，每阶段可独立交付、独立验证。**P1 已完成（2026-07-31）**，后因设计变更（wechat 由子进程改为 in-process 托管，见 [architecture.md §1.1](./architecture.md)），P2 重新规划并已完成；**P2、P3 均已完成（2026-07-31）**。

## 阶段总览

| 阶段 | 主题 | 主要交付 | 验证 |
|---|---|---|---|
| ~~P1~~ | ~~wechat gateway 进程内 admin server~~ | ~~admin socket + 状态机 + lock/pid~~ | ~~已完成；其 server.py/pid 在 P2 移除~~ |
| ~~P2~~ | ~~gateway config-driven 多 channel + WechatRuntime in-process~~ | ~~ChannelWechat 模型 + gateway 多 channel 调度 + WechatRuntime + 精简 wechat_admin + workspace_console router + 持久化 enable~~ | ~~已完成；单测 + 手动 curl 通过~~ |
| ~~P3~~ | ~~前端三页 + header~~ | ~~Me / console / wechat admin 页 + ChatWindow header Me 按钮~~ | ~~已完成；build + 端到端走查通过~~ |
| P4 | 文档收尾 + 单测补全 | 同步现有文档、补全测试 | `uv run pytest` 相关用例 |

每阶段结束更新 [TASKS.md](/TASKS.md)。

---

## P1 — wechat gateway 进程内 admin server（已完成）

状态：**已完成（2026-07-31）**。交付物与验证见 [TASKS.md 2026-07-31 记录](/TASKS.md)。

P1 产物中：
- `wechat_admin/state.py`、`wechat_channel.py` 改造（`_run_thread`/`_wrap_login`/`request_stop`）、`lifecycle.py` 的 `acquire_lock`/`lock_path` → **P2 保留**。
- `wechat_admin/server.py`（UDS admin server）、`lifecycle.py` 的 `write_pid`/`clear_pid`/`pid_path`、`session_acceptor.py` 的 `WechatSessionAcceptor` → **P2 移除**（in-process 后无需 IPC 与子进程管理）。

---

## P2 — gateway config-driven 多 channel + WechatRuntime in-process（已完成）

状态：**已完成（2026-07-31）**。交付物与验证见 [TASKS.md 2026-07-31 记录](/TASKS.md)。

目标：gateway 支持 config-driven 多 channel in-process 启动；wechat 由 `WechatRuntime` 托管；web console router 可控制启停并持久化 enable。

### 交付物

1. `src/everlingo/models.py` — 新增 `ChannelWechat`，`Channels` 加 `channel_wechat` 字段
   - `ChannelWechat.enable: bool = False`
   - 见 architecture §7.1
2. `src/everlingo/gateway/gateway.py` 改造
   - `_parse_args`：保留三 flag（`mutually_exclusive_group` 不变）
   - `_run` / `Gateway.run` 分两路：
     - explicit flag（`--channel_stdio/wechat/web`）→ 单 acceptor（`--channel_web` 额外带 idle `WechatRuntime(auto_start=False)` 供 console 控制）
     - 无参 → 读 `plugins.channels`：`channel_web` 节点存在且 enable → `WebSessionAcceptor`；`channel_wechat` enable → `WechatRuntime(auto_start=True)`；web 存在但 wechat 未 enable → 额外 `WechatRuntime(auto_start=False)`
     - `asyncio.gather(*acceptor_tasks)`；任一 acceptor 异常退出 → 触发 gateway shutdown（set 所有 runtime `_stop_event` + cancel web）→ gather 完成 → 退进程
   - `Gateway` 暴露 `wechat_runtime` 属性（供 router 访问）
   - 见 architecture §4.2、§4.6
3. `src/everlingo/gateway/wechat_admin/runtime.py` — 新增 `WechatRuntime`
   - 实现 `SessionAcceptor.start(gateway) -> task`（supervisor task）
   - `_start_wechat()`：`acquire_lock`（失败 → conflict 态）→ `WechatChannel(on_logined=self._on_logined)` → `await channel.init()` → `gateway.accept_session`
   - `start_wechat()` / `stop_wechat()` / `status()`：console 控制接口
   - `_on_logined()`：`save_setting` 写 `channel_wechat.enable=true`（节点不存在则补写）
   - `stop_wechat()`：`request_stop` → 等 `wait_run_done`（超时 10s）→ 释放锁 → `save_setting(enable=false)`
   - standalone 模式（`--channel_wechat`）：`start()` 内 `loop.add_signal_handler(SIGINT/SIGTERM, ...)` → `stop_wechat()`
   - 见 architecture §4.1、§4.4、§4.5
4. `src/everlingo/gateway/wechat_admin/lifecycle.py` 简化
   - 保留 `acquire_lock`/`lock_path`/`LockAcquireError`
   - 删 `write_pid`/`clear_pid`/`pid_path`
5. `src/everlingo/gateway/wechat_admin/server.py` — 删除
6. `src/everlingo/gateway/wechat_admin/__init__.py` — 更新注释（删「web 不 import」边界声明）
7. `src/everlingo/gateway/session_acceptor.py` — 删 `WechatSessionAcceptor`（被 `WechatRuntime` 取代）
8. `src/everlingo/gateway/workspace_console/router.py` — 新增
   - `GET /api/wechat-channel/status` / `POST /start` / `POST /stop` 直调 `gateway.wechat_runtime`
   - 经 `web_acceptor` 既有 `_gateway` 全局访问 gateway
   - 见 architecture §5.2
9. `src/everlingo/gateway/web_acceptor.py` 改造
   - `app.include_router(workspace_console_router)`
   - 静态页 fallback：`/console/me`、`/console/web-console`、`/console/web-console/{path}`（早于 catch-all）
   - 见 architecture §5.1、§5.3
10. `deploy/ws-container/root/app/entrypoint.sh:35` — `python -m everlingo gateway --channel_web` → `python -m everlingo gateway`（config-driven）

### 验证

```bash
# 无参 config-driven：channel_web + channel_wechat(若 enable) 同进程启动
uv run python -m everlingo.gateway &
# web console 启停
curl -X POST http://localhost:8000/api/wechat-channel/start
curl http://localhost:8000/api/wechat-channel/status
curl -X POST http://localhost:8000/api/wechat-channel/stop
# standalone wechat 仍可用
uv run python -m everlingo.gateway --channel_wechat &
# 锁冲突：web 内 start 时 standalone 占锁 → status 返回 conflict
```

单测：
- `tests/gateway/wechat_admin/test_runtime.py`：mock `WechatChannel` + `acquire_lock`，验证 start/stop/status/conflict/on_logined 写 enable、stop 写 enable=false
- `tests/gateway/test_gateway_multichannel.py`：无参 → 按 config 起 web+wechat acceptor；explicit flag → 单 acceptor；`--channel_web` 带 idle runtime
- `tests/gateway/workspace_console/test_router.py`：FastAPI TestClient 对 router 全端点（mock runtime）
- `tests/gateway/wechat_admin/test_lifecycle.py`：删 pid 用例，保留 lock 用例
- `tests/gateway/wechat_admin/test_server.py`：删除（server.py 已删）

### 本阶段不包含

- 前端页面（P3）；router 已就绪可被前端调，但前端尚未建。

---

## P3 — 前端三页 + header（已完成）

状态：**已完成（2026-07-31）**。交付物与验证见 [TASKS.md 2026-07-31 记录](/TASKS.md)。

### 交付物

1. `web/vite.config.ts`：`rollupOptions.input` 增 `me`、`web-console` entry
2. `web/me.html`、`web/web-console.html`（仿 `web/editor.html`）
3. `web/src/me/main.tsx`、`web/src/me/MePage.tsx`：一个「Workspace Console」按钮 → `/console/web-console`
4. `web/src/web-console/main.tsx`、`web/src/web-console/ConsolePage.tsx`：列出 channels admin 下入口（本期仅 wechat）
5. `web/src/web-console/WechatChannelAdmin.tsx`、`web/src/web-console/useWechatChannelStatus.ts`
   - hook：2s 轮询 `GET /api/wechat-channel/status`
   - UI：按 `running` + `state` 渲染（见 architecture §6.4，含 `stopped`/`conflict` 态）
   - `[打开扫码页]`：`window.open(qr_url, "_blank", "noopener")`
   - `last_error` 红色 banner
6. `web/src/components/ChatWindow.tsx`：header 加 `Me` 按钮（architecture §6.3）

### 验证

```bash
cd web && npm run build
uv run python -m everlingo.gateway &
# 浏览器打开 http://localhost:8000/
# 点 header [Me] → /console/me → [Workspace Console] → /console/web-console
# 点 wechat channel admin → /console/web-console/plugins/channels/wechat_channel/admin
# 点 [启动] → 等 status running=true, state=waiting_scan
# 点 [打开扫码页] → 新 Tab 打开 QR 网页 → 手机扫码
# 状态流转 waiting_scan → scanned → logined
# 重启进程 → 确认 wechat 自动恢复（state=logined，无需扫码）
```

无单测（前端），靠端到端走查。`npm run build` 必须 tsc 通过。

### 本阶段不包含

- 单测补全（P4）

---

## P4 — 文档收尾 + 单测补全

目标：补齐测试覆盖与跨文档引用，更新任务跟踪。

### 交付物

1. 补全 P2 漏的单测（若 P2 已覆盖则跳过）
2. 更新 [channel-wechat-ilink.md](../channel-wechat-ilink.md)：加「in-process 托管 + on_logined 持久化 + 自动启动」一节（P2 已部分完成，此处校对）
3. 更新 [web-chatbot.md](../web-chatbot.md) §Header：记录 `Me` 按钮
4. 更新 [web-session-acceptor.md](../web-session-acceptor.md)：记录 workspace console router 挂载与静态页 fallback
5. 更新 [gateway.md](../gateway.md)：记录 config-driven 多 channel 与 explicit flag 语义
6. 更新 [configuration.md](../configuration.md) 与 [user-docs/reference/configuration.md](/user-docs/reference/configuration.md)：记录 `channel_wechat.enable` 字段
7. 更新 [TASKS.md](/TASKS.md)：记录全部已完成项
8. 更新 [STATE.md](/STATE.md)（如需要）

### 验证

```bash
uv run pytest tests/gateway/wechat_admin tests/gateway/workspace_console tests/gateway/test_gateway_multichannel -v
cd web && npm run build   # tsc 通过
```

---

## 跨阶段约束

- **P2 是核心重构**：gateway 多 channel 调度 + WechatRuntime + 精简 wechat_admin + router + 持久化 enable，内聚交付。
- **P3 依赖 P2**：前端依赖 `/api/wechat-channel/*` 与 config-driven 自动恢复行为。
- **P3 可与 P4 部分并行**：前端开发期间可同步校对文档。
- 每阶段结束跑相关单测 + `npm run build`（P3 起），确认通过后再进下一阶段。
- wechatbot SDK 无单测（依 [channel-wechat-ilink.md §注意事项](../channel-wechat-ilink.md)），runtime / state / lifecycle / router / gateway 均用 mock，不真起 SDK。
