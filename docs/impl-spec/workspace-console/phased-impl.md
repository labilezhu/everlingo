# Workspace Console — 分阶段实施计划

按依赖顺序分 4 个阶段，每阶段可独立交付、独立验证。阶段间无强耦合回退——前一阶段未完成不影响后续阶段代码编译，但功能链路需累积到 §4 才端到端可用。

## 阶段总览

| 阶段 | 主题 | 主要交付 | 验证 |
|---|---|---|---|
| P1 | wechat gateway 进程内 admin server | admin socket + 状态机 + lock/pid | `curl --unix-socket` 探活；状态机单测 |
| P2 | web 进程内 lifecycle + router | 启停子进程 + `/api/wechat-channel/*` | 手动 curl 调启停；lifecycle 单测 |
| P3 | 前端三页 + header | Me / console / wechat admin 页 + ChatWindow header Me 按钮 | 浏览器端到端走查 |
| P4 | 文档收尾 + 单测补全 | 同步现有文档、补全测试 | `uv run pytest` 相关用例 |

每阶段结束更新 [TASKS.md](/TASKS.md)。

---

## P1 — wechat gateway 进程内 admin server

目标：让 `--channel_wechat` 进程通过 UDS 暴露状态与 shutdown，并具备单例锁定。

### 交付物

1. `src/everlingo/gateway/wechat_admin/__init__.py`
2. `src/everlingo/gateway/wechat_admin/state.py` — `WechatAdminState` 线程安全状态机
   - 字段：`state`、`qr_url`、`last_error`（含 `at` 时间戳）
   - 方法：`set(state=, qr_url=)`、`set_last_error(err)`、`snapshot()` 返回 dict
   - 线程安全：`threading.Lock`（SDK 回调来自 bot 线程，admin server 读取来自 uvicorn 线程）
3. `src/everlingo/gateway/wechat_admin/lifecycle.py` — lock + pid
   - `acquire_lock() -> int`：flock `LOCK_EX | LOCK_NB` on `gateway.lock`，失败 `SystemExit`。返回 fd（全程持有）
   - `write_pid()` / `clear_pid()`：`gateway.pid`，`atexit.register(clear_pid)`
4. `src/everlingo/gateway/wechat_admin/server.py` — FastAPI app + uvicorn over UDS
   - `create_admin_app(state: WechatAdminState, bot: WeChatBot) -> FastAPI`
   - 端点：`GET /status`、`GET /last_error`、`POST /shutdown`（调 `bot.stop()`）
   - `run_admin_server(uds_path, app)`：uvicorn `Config(app, uds=..., loop="asyncio")`，返回 task
5. `src/everlingo/gateway/channels/wechat_channel.py` 改造
   - `__init__` 新增 `self._admin_state = WechatAdminState(state="starting")`
   - `init()`：注入 `on_qr_url` / `on_scanned` / `on_expired` / `on_error` 回调更新 `_admin_state`；启动路径改 `threading.Thread(target=self._run_thread, daemon=True)`
   - `_run_thread()`：`asyncio.run(self._run())`
   - `_run()`：`_wrap_login()` → `await bot.login()` → `await bot.start()`
   - `_wrap_login()`：monkey-patch `bot.login` 注入 `logined` 与 `last_error`
6. `src/everlingo/gateway/session_acceptor.py` / `gateway.py` 改造
   - `WechatSessionAcceptor.start()`：`acquire_lock()` + `write_pid()` → 起 session task + admin server task 并行返回
   - admin socket 路径：`workspace.plugins_dir() / "channels" / "wechat_channel" / "channel_admin.sock"`（启动前删除残留 socket 文件）

### 验证

```bash
# 手动启动（应持有锁、起 admin server）
uv run python -m everlingo.gateway.gateway --channel_wechat &
# 另一终端探活
curl --unix-socket $workspace/plugins/channels/wechat_channel/channel_admin.sock \
     http://localhost/status
# 单例：第二个进程应退出
uv run python -m everlingo.gateway.gateway --channel_wechat   # 应报锁占用并退出
```

单测：
- `tests/gateway/wechat_admin/test_state.py`：回调序列 → 状态转移（含 `logined → waiting_scan` 重登、`on_error` 不改 state）
- `tests/gateway/wechat_admin/test_lifecycle.py`：lockfile 单例（mock flock，第二个 acquire 失败）

人手验证：
```bash
watch -d "curl --unix-socket $workspace/plugins/channels/wechat_channel/channel_admin.sock  http://localhost/status"
```


### 本阶段不包含

- web 侧调用（P2）
- 前端（P3）

---

## P2 — web 进程内 lifecycle + router

目标：`--channel_web` 进程能启停 wechat 子进程并聚合状态给前端。

### 交付物

1. `src/everlingo/gateway/workspace_console/__init__.py`
2. `src/everlingo/gateway/workspace_console/wechat_lifecycle.py`
   - `probe_admin_socket() -> bool`：连 `channel_admin.sock` 探活（httpx UDS transport，`GET /status` 3s 超时）
   - `is_pid_alive(pid) -> bool`：`os.kill(pid, 0)`
   - `read_pid() -> int | None`：读 `gateway.pid`
   - `start_wechat_gateway()`：socket probe + pid 判定后 `subprocess.Popen(...)`（参数见 architecture §4.2）
   - `stop_wechat_gateway()`：`POST /shutdown`（3s）→ `SIGTERM`（等 5s）→ `SIGKILL` → 清 `gateway.pid`
3. `src/everlingo/gateway/workspace_console/router.py` — FastAPI router
   - `GET /api/wechat-channel/status`：综合 socket probe + admin `GET /status` + `GET /last_error`
   - `POST /api/wechat-channel/start`：探活后条件启动，幂等
   - `POST /api/wechat-channel/stop`：调 `stop_wechat_gateway()`
4. `src/everlingo/gateway/web_acceptor.py` 改造
   - `app.include_router(workspace_console_router)`
   - 静态页 fallback：`/me`、`/web-console`、`/web-console/{path}`（早于 catch-all）

### 验证

```bash
uv run python -m everlingo.gateway.gateway --channel_web &
# 启动 wechat
curl -X POST http://localhost:8000/api/wechat-channel/start
# 查状态
curl http://localhost:8000/api/wechat-channel/status
# 停止
curl -X POST http://localhost:8000/api/wechat-channel/stop
```

单测：
- `tests/gateway/workspace_console/test_wechat_lifecycle.py`：mock subprocess + socket probe，验证「socket 在→不启」「socket 不在 + pid 不在→启」
- router 端点用 FastAPI TestClient + mock lifecycle

### 本阶段不包含

- 前端页面（P3）；router 已就绪可被前端调，但前端尚未建。

---

## P3 — 前端三页 + header

目标：浏览器端到端可用：从 chatbot header 进 Me → console → wechat channel admin，完成扫码登录。

### 交付物

1. `web/vite.config.ts`：`rollupOptions.input` 增 `me`、`web-console` entry
2. `web/me.html`、`web/web-console.html`（仿 `web/editor.html`）
3. `web/src/me/main.tsx`、`web/src/me/MePage.tsx`：一个「Workspace Console」按钮 → `/web-console`
4. `web/src/web-console/main.tsx`、`web/src/web-console/ConsolePage.tsx`：列出 channels admin 下入口（本期仅 wechat）
5. `web/src/web-console/WechatChannelAdmin.tsx`、`web/src/web-console/useWechatChannelStatus.ts`
   - hook：2s 轮询 `GET /api/wechat-channel/status`
   - UI：按 `running` + `state` 渲染（见 architecture §6.4）
   - `[打开扫码页]`：`window.open(qr_url, "_blank", "noopener")`
   - `last_error` 红色 banner
6. `web/src/components/ChatWindow.tsx`：header 加 `Me` 按钮（architecture §6.3）

### 验证

```bash
cd web && npm run build
uv run python -m everlingo.gateway.gateway --channel_web &
# 浏览器打开 http://localhost:8000/
# 点 header [Me] → /me → [Workspace Console] → /web-console
# 点 wechat channel admin → /web-console/plugins/channels/wechat_channel/admin
# 点 [启动] → 等 status running=true, state=waiting_scan
# 点 [打开扫码页] → 新 Tab 打开 QR 网页 → 手机扫码
# 状态流转 waiting_scan → scanned → logined
```

无单测（前端），靠端到端走查。`npm run build` 必须 tsc 通过。

### 本阶段不包含

- 单测补全（P4）

---

## P4 — 文档收尾 + 单测补全

目标：补齐测试覆盖与跨文档引用，更新任务跟踪。

### 交付物

1. 补 `tests/gateway/wechat_admin/test_server.py`：FastAPI TestClient 对 `create_admin_app`，验证 `/status`、`/last_error`、`/shutdown`（mock bot.stop）
2. 补 `tests/gateway/workspace_console/test_router.py`：TestClient 对 router 全端点
3. 更新 [channel-wechat-ilink.md](../channel-wechat-ilink.md)：加「admin socket 与生命周期管理」一节，指向本目录
4. 更新 [web-chatbot.md](../web-chatbot.md) §Header：记录 `Me` 按钮
5. 更新 [web-session-acceptor.md](../web-session-acceptor.md)：记录 workspace console router 挂载与静态页 fallback
6. 更新 [TASKS.md](/TASKS.md)：记录全部已完成项
7. 更新 [STATE.md](/STATE.md)（如需要）

### 验证

```bash
uv run pytest tests/gateway/wechat_admin tests/gateway/workspace_console -v
cd web && npm run build   # tsc 通过
```

---

## 跨阶段约束

- **P1 必须先于 P2**：admin socket 是 P2 lifecycle 探活对象。
- **P2 必须先于 P3**：前端依赖 `/api/wechat-channel/*`。
- **P3 可与 P4 部分并行**：前端开发期间可同步补 P1/P2 单测。
- 每阶段结束跑相关单测 + `npm run build`，确认 tsc 通过后再进下一阶段。
- wechatbot SDK 无单测（依 [channel-wechat-ilink.md §注意事项](../channel-wechat-ilink.md)），admin server / state / lifecycle 均用 mock，不真起 SDK。
