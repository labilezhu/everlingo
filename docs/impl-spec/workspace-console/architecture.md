# Workspace Console — 架构设计

## 1. 概览

Workspace Console 是 `--channel_web` 进程内的一个 FastAPI router 子模块 + 一组静态前端页面。它**不新增进程**，而是复用 8000 端口的 Web Session Acceptor（[web-session-acceptor.md](../web-session-acceptor.md)）既有的 FastAPI app。

它管理的对象是**其它 channel 的 gateway 子进程**（首个：wechat gateway），通过 Unix Domain Socket（UDS）与之通信。

```
┌─────────────────────────────────────────────────────────────┐
│  --channel_web 进程（FastAPI on :8000）                       │
│                                                              │
│  ┌──────────────┐  ┌─────────────────┐  ┌───────────────┐  │
│  │ Web Session  │  │ Vault Editor API │  │ Workspace     │  │
│  │ Acceptor     │  │ router           │  │ Console router│  │
│  │ (chatbot)    │  │ (existing)       │  │ (new)         │  │
│  └──────────────┘  └─────────────────┘  └──────┬───────┘  │
│                                                  │           │
│                                  ┌───────────────┴────────┐  │
│                                  │ wechat lifecycle mgr   │  │
│                                  │ (subprocess + lock)   │  │
│                                  └───────────┬───────────┘  │
└──────────────────────────────────────────────┼──────────────┘
                                               │ spawn / kill
                                               ▼
┌──────────────────────────────────────────────────────────────┐
│  --channel_wechat 进程（独立 OS 进程）                          │
│                                                              │
│  ┌──────────────┐   thread   ┌────────────────────────────┐  │
│  │ WechatSession│            │ WeChatBot (sdk)           │  │
│  │ Acceptor     │            │  └ login() / start()      │  │
│  └──────────────┘            └────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ wechat admin server (FastAPI over UDS)               │   │
│  │  socket: $workspace/plugins/channels/                │   │
│  │           wechat_channel/channel_admin.sock           │   │
│  │  GET /status · GET /last_error · POST /shutdown      │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### 1.1 为何 wechat gateway 保持独立进程

- **保留手动启动用法**：`python -m everlingo.gateway.gateway --channel_wechat` 仍是合法且完整的入口，用户可在无 web 环境下直接跑。
- **进程隔离**：wechat SDK 阻塞 `bot.run()`、依赖网络长轮询，独立进程避免拖累 web 进程的 asyncio loop。
- **生命周期解耦**：web 进程退出时 wechat 子进程可继续运行（`start_new_session=True` 解耦），下次 web 重启后重新 attach。
- 代价：需要一套 IPC + 单例锁定。IPC 范式复用 [memory-vault-search-spec.md](../search/memory-vault-search-spec.md) 已建立的 UDS + FastAPI 模式，不引入新模式。

### 1.2 为何 admin server 复用 UDS 而非 TCP

- 同机通信，UDS 免端口占用、免网络栈、天然具备「文件路径即地址」的 workspace 隔离语义。
- 与 `indexer.sock`（`$workspace/indexer.sock`）一致：admin socket 放 `$workspace/plugins/channels/wechat_channel/channel_admin.sock`，按 channel 维度隔离。
- UDS 文件本身可用作「进程存活探针」（文件存在 + 可连接 ≈ 进程在跑）。

## 2. 进程拓扑与职责

### 2.1 `--channel_web` 进程内新增

| 模块 | 文件 | 职责 |
|---|---|---|
| workspace console router | `src/everlingo/gateway/workspace_console/router.py` | FastAPI router，挂到 `web_acceptor.app`，提供 `/api/wechat-channel/*` 与 `/me`、`/web-console` 静态页 fallback |
| wechat lifecycle manager | `src/everlingo/gateway/workspace_console/wechat_lifecycle.py` | `acquire_lock` / `probe_admin_socket` / `start_wechat_gateway` / `stop_wechat_gateway` |
| 前端入口 | `web/me.html` + `web/web-console.html` + `web/src/me/` + `web/src/web-console/` | Me 页、console 首页、wechat channel admin 页 |

### 2.2 `--channel_wechat` 进程内新增

| 模块 | 文件 | 职责 |
|---|---|---|
| wechat admin server | `src/everlingo/gateway/wechat_admin/server.py` | FastAPI app + uvicorn over UDS，与 session task 并行跑在主 asyncio loop |
| admin state | `src/everlingo/gateway/wechat_admin/state.py` | 线程安全状态机 `WechatAdminState`，由 SDK 回调更新，admin server 读取 |
| lifecycle（lock + pid） | `src/everlingo/gateway/wechat_admin/lifecycle.py` | `acquire_lock`（fcntl.flock 独占）、`write_pid`、退出清理 |

`WechatChannel`（`src/everlingo/gateway/channels/wechat_channel.py`）改造：注入 SDK 回调、启动路径由 `bot.run()` 改为 `asyncio.run(self._run())`（见 §3.4）。

### 2.3 谁不做什么

- **web 进程不直接调 `WeChatBot`**：所有 wechat 操作经 admin socket IPC，不导入 wechatbot SDK。
- **admin server 不做业务决策**：只暴露状态与 shutdown，不转发聊天消息（聊天走既有 Session/WebChannel 路径）。
- **wechat 子进程不知道 web 进程存在**：单向被管理，解耦。

## 3. 状态机与 IPC 协议

### 3.1 Wechat channel 状态

admin server `GET /status` 返回的 `state` 取值：

| state | 含义 | qr_url |
|---|---|---|
| `starting` | 进程已起、bot 尚未到登录阶段 | `null` |
| `waiting_scan` | 已发 QR-Code 网页地址，等待用户扫码 | 当前 QR 网页 URL |
| `scanned` | 用户已扫码、等待手机端确认 | `null`（或保留旧 QR） |
| `logined` | 登录成功、长轮询运行中 | `null` |
| `not_running` | 进程未运行（仅 web 侧综合判断，admin server 不会返回此值） | — |

**无 `error` 态**：错误不作为状态，改由 `GET /last_error` 独立接口提供最近一次错误信息。错误发生时 state 保持当前值或按 SDK 回调流转（见下）。

### 3.2 状态转移

```
            ┌───────────┐
进程启动 ──►│ starting  │
            └─────┬─────┘
                  │ on_qr_url(首次)
                  ▼
            ┌──────────────┐  on_expired / 新 QR 轮换
        ┌──►│ waiting_scan │────────────────────┐
        │   └──────┬───────┘                   │
        │          │ on_scanned                │
        │          ▼                           │
        │   ┌────────────┐                      │
        │   │  scanned   │                      │
        │   └──────┬─────┘                      │
        │          │ login() 返回              │
        │          ▼                           │
        │   ┌────────────┐                      │
        │   │  logined   │                      │
        │   └──────┬─────┘                      │
        │          │ session expired (重登)     │
        └──────────┘  on_qr_url(重登) ──────────┘
```

关键转移规则：
- `logined → waiting_scan`：长轮询中 session expired，SDK `clear_credentials` + `login(force=True)` 会重新触发 `on_qr_url`。
- `logined` 注入点：SDK 无 `on_logged_in` 回调（见 [channel-wechat-ilink.md](../channel-wechat-ilink.md) / `wechatbot/auth.py`）。首登在 `WechatChannel._run()` 内 `await bot.login()` 返回后置 `logined`。**重登后的 `logined`** 由 monkey-patch `bot.login` 捕获（见 §3.4）。
- `on_error`：只写 `last_error`，不改 state。错误可能是瞬时（重试中）或重登失败，UI 显示但不阻断状态展示与 QR 按钮。

### 3.3 Admin socket 接口

HTTP/1.1 over UDS，REST + JSON。uvicorn 绑定 `$workspace/plugins/channels/wechat_channel/channel_admin.sock`。

| 方法 | 路径 | 响应 | 说明 |
|---|---|---|---|
| GET | `/status` | `{state: "starting"\|"waiting_scan"\|"scanned"\|"logined", qr_url: str\|null}` | 当前 channel 状态与扫码 URL |
| GET | `/last_error` | `{message: str, at: ISO8601}` 或 `{}` | 最近一次错误；无错误返回空对象 |
| POST | `/shutdown` | `{ok: true}` | 调 `bot.stop()` 优雅退出长轮询，进程随后退出 |

所有端点供 `--channel_web` 进程的 lifecycle manager 调用，也支持 `curl --unix-socket` 手工调试（与 `indexer.sock` 一致）。

### 3.4 `logined` 注入与启动路径改造

现状（`wechat_channel.py:77`）：

```python
bot_thread = threading.Thread(target=self._bot.run, daemon=True)
```

`bot.run()` 内部 `asyncio.run(self._run_sync())`，`_run_sync` 调 `await self.login()` 后 `await self.start()`。login 在 SDK 内部调用，无法外挂回调。

改造方案：**不调 `bot.run()`**，改在独立线程内跑自定义 `_run()`：

```python
async def _run(self) -> None:
    # 首登
    self._wrap_login()              # monkey-patch bot.login 以注入 logined
    await self._bot.login()         # 触发 patch，成功后 state=logined
    await self._bot.start()         # 长轮询；session expired 时内部重登也走 patch

def _wrap_login(self) -> None:
    orig = self._bot.login
    state = self._admin_state
    async def wrapped(*a, **kw):
        try:
            creds = await orig(*a, **kw)
            state.set(state="logined", qr_url=None)
            return creds
        except Exception as e:
            state.set_last_error(e)
            raise
    self._bot.login = wrapped
```

- monkey-patch 覆盖首登与 `start()` 内部 session-expired 重登两条路径，统一注入 `logined`。
- `bot.start()` 阻塞至 `bot.stop()`，`POST /shutdown` 调 `bot.stop()` 让其退出。
- `on_qr_url` / `on_scanned` / `on_expired` / `on_error` 四个回调由 `WeChatBot.__init__` 注入，更新 `WechatAdminState`。

## 4. 单例与生命周期管理

### 4.1 单例锁定

「不能有多个 Wechat gateway 进程」由双重机制保证：

1. **lockfile 独占锁**（强约束）：`--channel_wechat` 进程在 `gateway._run` 的 wechat 分支入口 `acquire_lock()`，`fcntl.flock(fd, LOCK_EX | LOCK_NB)` on `$workspace/plugins/channels/wechat_channel/gateway.lock`。拿不到即 log error + 退出。flock 在进程退出（含崩溃）时自动释放。
2. **socket probe**（健康判断）：web 侧 `start_wechat_gateway()` 启动前先 `probe_admin_socket()` 连 `channel_admin.sock`：
   - 可连 → 进程在跑，不重复启动，返回「已在运行」。
   - 不可连 → 再按 pid 文件判进程存活（`os.kill(pid, 0)`）：
     - 进程在但 socket 不响应 → 状态异常，提示用户手动 stop / kill。
     - 进程不在 → 启动新进程。

lockfile 保证「不会有两个进程同时跑」；socket probe 保证「web 侧不会盲启第二个」。

### 4.2 子进程启动

`start_wechat_gateway()`（web 进程内）：

```python
subprocess.Popen(
    [sys.executable, "-m", "everlingo.gateway.gateway", "--channel_wechat"],
    stdout=open(log_path, "a"),
    stderr=subprocess.STDOUT,
    stdin=subprocess.DEVNULL,
    start_new_session=True,   # 解耦：web 退出时 wechat 继续跑
    cwd=workspace.root(),
    env={**os.environ, "EVERLINGO_WORKSPACE_DIR": str(workspace.root())},
)
```

- 日志重定向到 `$workspace/logs/wechat-gateway.log`。
- pid 写 `$workspace/plugins/channels/wechat_channel/gateway.pid`（由子进程自己写，见 §4.3）。
- `start_new_session=True`：脱离 web 进程的 session/process group，web 崩溃不带走 wechat。

### 4.3 子进程内的 lock + pid

`wechat_admin/lifecycle.py`（在 `--channel_wechat` 进程内）：

- `acquire_lock()`：flock 独占锁，失败退出。锁 fd 全程持有（不关闭），进程退出自动释放。
- `write_pid()`：写 `gateway.pid`，退出时清理（`atexit` + `try/finally`）。
- lockfile 与 pid 文件同目录：`$workspace/plugins/channels/wechat_channel/`。

### 4.4 停止语义

`stop_wechat_gateway()`（web 进程内）优先优雅：

1. `POST /shutdown`（admin socket，3s 超时）→ `bot.stop()` → 长轮询退出 → 进程退出。
2. 超时或 socket 不可连 → 读 `gateway.pid` → `os.kill(pid, SIGTERM)`，再等若干秒。
3. 仍存活 → `SIGKILL`。
4. 清理 `gateway.pid`、`channel_admin.sock`（socket 文件由 admin server 退出时清理或下次启动覆盖）。

### 4.5 迁移说明

加入 lockfile 后，**现存手动启动的 wechat gateway 进程（无锁）必须重启一次**才能被 console 管理。重启后该进程持有锁，web 侧 socket probe 可正常探活。此为已知一次性迁移成本，已确认接受。

## 5. web_acceptor 集成

### 5.1 router 挂载

`web_acceptor.py`（既有）在 `app.include_router(vault_editor_router)` 之后新增：

```python
from everlingo.gateway.workspace_console.router import router as workspace_console_router
app.include_router(workspace_console_router)
```

### 5.2 API 端点

workspace console router 暴露（前缀 `/api/wechat-channel`）：

| 方法 | 路径 | 行为 |
|---|---|---|
| GET | `/api/wechat-channel/status` | 综合：socket probe + pid → 返回 `{running: bool, state?, qr_url?, last_error?}`。`running=false` 时其余字段省略 |
| POST | `/api/wechat-channel/start` | 探活后若 not_running 才 `start_wechat_gateway()`；已运行则幂等返回 |
| POST | `/api/wechat-channel/stop` | 调 `stop_wechat_gateway()`（优雅 → SIGTERM → SIGKILL） |

### 5.3 静态页 fallback

仿 `/editor`（`web_acceptor.py:129`）新增 SPA fallback：

- `GET /me` → `web/dist/me.html`
- `GET /web-console`、`GET /web-console/{path}` → `web/dist/web-console.html`

均早于 catch-all `/{path:path}` 注册。

## 6. 前端结构

### 6.1 构建入口

`web/vite.config.ts` 的 `rollupOptions.input` 增两个 entry（沿用 `/editor` 模式）：

```ts
input: {
  main: 'index.html',
  editor: 'editor.html',
  me: 'me.html',
  'web-console': 'web-console.html',
}
```

新增 `web/me.html`、`web/web-console.html`（结构同 `web/editor.html`，引用各自 `src/*/main.tsx`）。

### 6.2 目录

```
web/src/
  me/
    main.tsx          # Me 页入口
    MePage.tsx
  web-console/
    main.tsx          # Console 首页入口
    ConsolePage.tsx
    WechatChannelAdmin.tsx
    useWechatChannelStatus.ts   # 2s 轮询 hook
```

### 6.3 ChatWindow header 改动

`web/src/components/ChatWindow.tsx` header（现「笔记编辑器」按钮，line 112）右侧加 `Me` 按钮：

```tsx
{!embedded && (
  <div className="flex items-center gap-1">
    <Button variant="ghost" size="sm" onClick={() => { window.location.href = '/editor'; }}>
      <NotebookPen /><span className="hidden md:inline">笔记</span>
    </Button>
    <Button variant="ghost" size="sm" onClick={() => { window.location.href = '/me'; }}>
      <User /><span className="hidden md:inline">Me</span>
    </Button>
  </div>
)}
```

移动端适配遵循 [web-chatbot.md §移动端适配](../web-chatbot.md)：图标常驻，文字 `hidden md:inline`。图标用 `lucide-react` 的 `User`。

### 6.4 WechatChannelAdmin 交互

`useWechatChannelStatus` 每 2s `GET /api/wechat-channel/status`。UI 按返回渲染：

| running | state | UI |
|---|---|---|
| false | — | 「Wechat gateway 未运行」+ `[启动]` 按钮 |
| true | starting | 「启动中…」+ `[停止]` |
| true | waiting_scan | 「等待扫码」+ `[打开扫码页]`（`window.open(qr_url)` 新 Tab）+ `[停止]` |
| true | scanned | 「已在手机确认，等待登录完成」+ `[停止]` |
| true | logined | 「已登录 ✅」+ `[停止]` |

`last_error` 非空时，UI 顶部红色 banner 显示 message，不阻断当前状态展示与按钮。

### 6.5 无客户端路由

项目不用 react-router（`/editor` 走 `window.location.href` 全页跳转）。`/me`、`/web-console` 沿用同模式，各自独立 entry。`/web-console` 下子页（wechat channel admin）目前单一，无需客户端路由；将来多子项时用 hash 或 query 区分。

## 7. 安全与边界

- **默认 localhost**：`plugins.channels.channel_web.listener.interface` 默认 `localhost`，console 与 admin socket 仅本机可达。
- **CORS**：`web_acceptor.py` 现有 `allow_origins=["*"]`（[web-session-acceptor.md §CORS](../web-session-acceptor.md)）。console 的 `/api/wechat-channel/*` 同源访问，不受 CORS 影响；但 `allow_origins=["*"]` 意味着任意可达 8000 的网页可调启停接口。公网部署时须收敛白名单 + 加鉴权，本期不做。
- **不暴露 secrets**：admin socket 只传状态与 shutdown 命令，不传 credentials（credentials 由 SDK 自管于 `credentials.json`，见 [channel-wechat-ilink.md §sdk 保存用户 credentials](../channel-wechat-ilink.md)）。
- **进程管理边界**：web 进程只管启/停 wechat 子进程，不介入其聊天消息收发（聊天走既有 Session/WebChannel 路径，见 [gateway.md](../gateway.md)）。

## 8. 与现有架构的契合

- 复用 `web_acceptor.py` 的 FastAPI app，不新增 server。
- IPC 范式复用 [memory-vault-search-spec.md](../search/memory-vault-search-spec.md) 的 UDS + FastAPI/uvicorn。
- 前端复用 [web-chatbot.md](../web-chatbot.md) 技术栈与多入口构建。
- wechat gateway 内部改造限于 `wechat_channel.py` 启动路径与回调注入，不影响 Session/WebChannel 的聊天收发协议。
- 不引入新依赖（FastAPI/uvicorn/httpx 已在依赖中；前端无新运行时依赖）。

## 9. 扩展位

- `channels admin` 下将来可加其它 channel admin（如 stdio channel 调试页），共用 `/web-console/plugins/channels/{channel}/admin` 路径约定与 admin socket 范式。
- `Me` 页预留更多入口（profile、settings 等）。
- admin socket 协议为 REST/JSON，新增端点即可扩展（如 `/logs` 流式日志、`/metrics`）。
