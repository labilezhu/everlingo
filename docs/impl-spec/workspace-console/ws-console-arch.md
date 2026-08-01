# Workspace Console — 架构设计

## 1. 概览

Workspace Console 是 web 进程内 FastAPI app 的一组 router + 一组静态前端页面，**不新增进程**。它复用 8000 端口的 Web Session Acceptor（[web-session-acceptor.md](../web-session-acceptor.md)）既有的 FastAPI app。

它管理的对象是**同进程内的 wechat channel 实例**——由 `WechatRuntime`（实现 `SessionAcceptor` 协议）托管，web console 经 router 直接调用其内存方法（状态读取 / 启停），不经 IPC。

```
┌──────────────────────────────────────────────────────────────────┐
│  gateway 进程（python -m everlingo.gateway [无参 | --channel_X]）  │
│                                                                   │
│  Gateway.run                                                      │
│    explicit --channel_X → 单 acceptor                             │
│    无参 → 读 everlingo.yaml.plugins.channels                      │
│           凡节点存在且 enable!=false 的 channel 起 acceptor       │
│           asyncio.gather 所有 acceptor supervisor task            │
│                                                                   │
│  ┌─────────────────────────┐  ┌─────────────────────────────────┐ │
│  │ WebSessionAcceptor      │  │ WechatRuntime (SessionAcceptor) │ │
│  │ FastAPI on :8000        │  │  acquire_lock（跨进程单例）      │ │
│  │  ├ chatbot router       │  │  WechatChannel（bot 线程）       │ │
│  │  ├ vault_editor router  │  │  WechatAdminState（内存）       │ │
│  │  ├ workspace_console ◄──┼──┤  on_logined → 写 enable=true     │ │
│  │  │   router（直调）     │  │  stop → 写 enable=false          │ │
│  │  └ 静态页 fallback     │  │  supervisor task（idle/running） │ │
│  └─────────────────────────┘  └─────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

### 1.1 为何 wechat channel 改为 in-process 托管（2026-07 设计变更）

原计划（P1 已实现）让 wechat gateway 跑在独立子进程、web 经 UDS admin socket 管理。经评估，子进程模型的维护成本（IPC + 单例锁 + pid 探活 + 信号收尾）超过收益，改为 **web 进程内 in-process 托管**。原 §1.1 给出的三条独立进程理由逐条复核：

- **asyncio loop 隔离**：P1 已把 `bot.run()` 换成 `_run_thread()` + 独立 `asyncio.new_event_loop()`，bot 长轮询跑在 daemon 线程的独立 loop 上，不拖累 web 进程的 asyncio loop。**此理由已被 P1 消解**。
- **生命周期解耦**（web 崩溃时 wechat 子进程可继续跑、web 重启后 re-attach）：in-process 后此属性消失——web 崩溃即丢失 wechat 会话。已确认接受：单用户本地场景 web 崩溃罕见；且 SDK 保存 `credentials.json`，重启后 `login(force=False)` 可免扫码自动恢复（见 [channel-wechat-ilink.md §分开 login](../channel-wechat-ilink.md)），配合 `channel_wechat.enable` 配置自动重启 wechat，体验已足够。
- **保留手动启动用法**：`python -m everlingo.gateway --channel_wechat` 仍是合法且完整的 standalone 入口（无 web 环境直接跑）。in-process 改造不影响它。

收益：少一个 OS 进程、少一套 IPC、调试更简单（单进程单日志流）；并为未来多 channel（telegram/discord/...）的 in-process 托管铺平范式。

### 1.2 为何不再用 UDS admin server

in-process 后 router 与 `WechatAdminState` 同进程，直接读 `state.snapshot()` 即可，无需 HTTP over UDS 中转。`wechat_admin/server.py`（P1 产物）整体移除。`wechat_admin/lifecycle.py` 的 `write_pid`/`clear_pid`/`pid_path` 一并移除（无子进程，无需 pid 探活）；保留 `acquire_lock`/`lock_path` 作为跨进程单例锁（防止 standalone `--channel_wechat` 与 web 内嵌 wechat 同时跑）。

## 2. 进程拓扑与职责

### 2.1 gateway 进程内模块

| 模块 | 文件 | 职责 |
|---|---|---|
| gateway 主入口 | `src/everlingo/gateway/gateway.py` | explicit flag → 单 acceptor；无参 → 读 config 多 channel + gather。提供 `start_channel`/`stop_channel` 运行时注册（供 console 动态启停 wechat） |
| web acceptor | `src/everlingo/gateway/web_acceptor.py`（既有，改） | 挂 `workspace_console_router`；新增 `/console/me`、`/console/web-console` 静态页 fallback |
| wechat runtime | `src/everlingo/gateway/wechat_admin/runtime.py`（新） | `WechatRuntime`：实现 `SessionAcceptor`；托管 wechat channel 生命周期；on_logined 持久化；console 启停接口 |
| workspace console router | `src/everlingo/gateway/workspace_console/router.py`（新） | `/api/wechat-channel/{status,start,stop}` 直调 `WechatRuntime` |
| admin state | `src/everlingo/gateway/wechat_admin/state.py`（P1，保留） | 线程安全状态机，router 直接读 `snapshot()` |
| lifecycle（lock） | `src/everlingo/gateway/wechat_admin/lifecycle.py`（P1，简化） | 仅 `acquire_lock`/`lock_path`（跨进程单例）；删 pid 相关 |
| 前端入口 | `web/me.html` + `web/web-console.html` + `web/src/me/` + `web/src/web-console/` | Me 页、console 首页、wechat channel admin 页 |

### 2.2 `WechatChannel`（既有，不改）

`src/everlingo/gateway/channels/wechat_channel.py` 保持 P1 改造后的形态：`init()` 起 daemon 线程跑 `_run_thread()`（独立 loop + main task），`_run()` 跑 `login()` + `start()`，`recv_envelope()` 用 `asyncio.to_thread(self._queue.get)` 不阻塞 web loop，`request_stop()` 跨线程取消。in-process 托管不需要再改它。

### 2.3 谁不做什么

- **router 不直接操作 `WechatChannel`**：经 `WechatRuntime` 的 `start()`/`stop()`/`status()` 方法，runtime 持有 channel 引用并管理锁。
- **runtime 不做业务决策**：只管启停 + 状态 + 持久化 enable，不介入聊天消息收发（聊天走既有 Session/WechatChannel 路径，见 [gateway.md](../gateway.md)）。
- **`WechatChannel` 不依赖 `setting` 模块**：持久化 enable 由 runtime 通过 `on_logined` 回调注入完成，channel 不导入 setting。

## 3. 状态机

### 3.1 Wechat channel 状态

`WechatAdminState.snapshot()` 返回的 `state` 取值（与 P1 一致）：

| state | 含义 | qr_url |
|---|---|---|
| `starting` | runtime 已起、bot 尚未到登录阶段 | `null` |
| `waiting_scan` | 已发 QR-Code 网页地址，等待用户扫码 | 当前 QR 网页 URL |
| `scanned` | 用户已扫码、等待手机端确认 | `null`（或保留旧 QR） |
| `logined` | 登录成功、长轮询运行中 | `null` |
| `stopped` | runtime 未启动 wechat（idle）/ 用户停止后 | — |
| `conflict` | acquire_lock 失败（standalone wechat 占用锁） | — |

新增 `stopped`（runtime idle，wechat 未跑）与 `conflict`（锁冲突）两个 runtime 综合态，由 router 在 `status()` 里据 runtime 状态判定，不写入 `WechatAdminState`（state.py 仍只含 SDK 驱动的四态）。

### 3.2 状态转移

P1 已定义的 SDK 驱动转移（`starting → waiting_scan → scanned → logined`、`logined → waiting_scan` 重登、QR 过期重试）不变，见 [P1 文档记录](../../TASKS.md) 与 `state.py`。in-process 改造新增的转移由 `WechatRuntime` 管理：

```
                  ┌─────────┐
  runtime.start() │ stopped │ ◄──────── 用户 stop / 启动后锁冲突解决
                  └────┬────┘
       acquire_lock ok │  + channel.init() + accept_session
       acquire_lock ✗ │
                  ┌────┴────┐
                  │ conflict │
                  └─────────┘
                       │ bot 线程跑起来
                       ▼
                 ┌───────────┐
                 │ starting  │ ──► SDK 驱动流转 ──► logined
                 └───────────┘                       │
                                                     │ on_logined 回调
                                                     ▼
                                              save enable=true
```

关键规则：
- **`on_logined` 注入**：runtime 在 `start()` 时向 `WechatChannel.init()` 传入 `on_logined` 回调（或经 channel 注入到 `_wrap_login`），login 成功后回调 `save_setting(channel_wechat.enable=true)`。若 yaml 中尚无 `channel_wechat` 节点，回调负责补写。
- **停止写 enable=false**：runtime `stop()` 在 bot 退出、锁释放后 `save_setting(channel_wechat.enable=false)`。用户主动停止 = 不再自动启动。
- **锁冲突不改 enable**：conflict 态下 enable 保持原值，UI 提示「wechat 已在 standalone 运行，请先停止」。

### 3.3 登录重试（AuthError 兜底）

P1 已实现：SDK 单次 `login()` 在 QR 连续过期 3 次后抛 `AuthError`，`WechatChannel._run()` 捕获后睡 `LOGIN_RETRY_INTERVAL=5.0` 重试，进程驻留 `waiting_scan`，`on_qr_url` 每轮清 `last_error`。in-process 不改此逻辑。

## 4. WechatRuntime 与生命周期管理

### 4.1 WechatRuntime 即 SessionAcceptor

`WechatRuntime` 实现 `SessionAcceptor` 协议（`start(gateway) -> asyncio.Task`），同时是 console 的控制句柄。它取代 P1 的 `WechatSessionAcceptor`。

```python
class WechatRuntime:
    def __init__(self, auto_start: bool) -> None:
        self._auto_start = auto_start   # config enable=true 时 True；idle 模式 False
        self._channel: WechatChannel | None = None
        self._session_id: str | None = None
        self._lock_fd: int | None = None
        self._gateway: Any = None
        self._stop_event = asyncio.Event()

    async def start(self, gateway) -> asyncio.Task:
        self._gateway = gateway
        if self._auto_start:
            await self._start_wechat()
        return asyncio.create_task(self._supervise())

    async def _supervise(self) -> None:
        await self._stop_event.wait()   # gateway shutdown 时 set

    # ── console 控制接口 ──
    async def start_wechat(self) -> dict: ...   # 幂等；调 _start_wechat
    async def stop_wechat(self) -> dict: ...    # request_stop + 等退出 + 释放锁 + 写 enable=false
    def status(self) -> dict: ...               # 综合 lock/channel/admin_state → snapshot

    async def _start_wechat(self) -> None:
        self._lock_fd = acquire_lock()  # 失败 → conflict 态，不抛、记状态
        self._channel = WechatChannel(on_logined=self._on_logined)
        await self._channel.init()
        self._session_id = str(uuid.uuid4())
        await self._gateway.accept_session(self._channel, self._session_id)

    def _on_logined(self) -> None:
        save_setting_channel_wechat(enable=True)
```

- `start()` 返回的 supervisor task 在 runtime 整个生命周期存活（即使 wechat 被 stop 进入 idle 也保持），仅 gateway shutdown 时 `_stop_event.set()` 退出。这保证 `asyncio.gather` 的 task 集稳定，wechat 启停不增删 gather 集。
- wechat 启停产生的 bot 线程 / session task 由 runtime 内部管理（session task 经 `gateway.accept_session` 注册，bot 线程经 `channel.wait_run_done` 监控），不直接进 gather。

### 4.2 acceptor 选择规则（gateway.py）

| 启动方式 | 创建的 acceptor | wechat 行为 |
|---|---|---|
| `--channel_wechat` | `WechatRuntime(auto_start=True)` 单独 | 忽略 config，强制启动 wechat；SIGINT/SIGTERM → `stop_wechat()` |
| `--channel_web` | `WebSessionAcceptor` + `WechatRuntime(auto_start=False)` | 忽略 config 的 wechat 项；wechat idle，console 可手动 start |
| `--channel_stdio` | `StdioSessionAcceptor` 单独 | 不创建 WechatRuntime（无 console，无控制入口） |
| 无参 | 读 config：`channel_web` enable → `WebSessionAcceptor`；`channel_wechat` enable → `WechatRuntime(auto_start=True)`；web 存在但 wechat 未 enable → 额外创建 `WechatRuntime(auto_start=False)` 供 console 手动控制 | wechat 按 config 自动启 |

- **explicit flag 忽略 config 多 channel 节点**：`--channel_X` 只跑指定的 X（`--channel_web` 额外带一个 idle WechatRuntime 仅为提供 console 控制能力，不自动启 wechat，不违反「只跑 web」）。
- **无参全 config 驱动**：凡 `plugins.channels` 下节点存在且 `enable != false` 的 channel 都启动。

### 4.3 跨进程单例锁

`acquire_lock()`（`wechat_admin/lifecycle.py`，flock `LOCK_EX|LOCK_NB` on `$workspace/plugins/channels/wechat_channel/gateway.lock`）保证「standalone wechat 与 web 内嵌 wechat 不同时跑」。

- `WechatRuntime._start_wechat()` 先 `acquire_lock()`，失败 → runtime 进入 `conflict` 态（不抛异常），console `status()` 返回 `state=conflict` + 提示。
- flock fd 全程持有，`stop_wechat()` 释放（`os.close`），进程退出自动释放。
- 原 P1 的 `write_pid`/`clear_pid`/`pid_path` 删除（无子进程，无需 pid 探活）。

### 4.4 停止语义

`WechatRuntime.stop_wechat()`：
1. `channel.request_stop()`（`bot.stop()` + 跨线程 `task.cancel()`，见 P1 `wechat_channel.py`）。
2. `await asyncio.to_thread(channel.wait_run_done)`（带超时，如 10s）。
3. 清理 session（gateway `_cleanup_session` 经 session task done callback 自动移除）。
4. `os.close(self._lock_fd)` 释放锁。
5. `save_setting(channel_wechat.enable=false)`。
6. runtime 回到 `stopped`/idle，supervisor task 仍存活（等 console 再次 start 或 gateway shutdown）。

### 4.5 standalone 信号优雅停（`--channel_wechat`）

standalone 模式无 admin server（P1 的 UDS admin server 已删），`WechatRuntime` 在 `start()` 时注册 `loop.add_signal_handler(SIGINT/SIGTERM, ...)` → 触发 `stop_wechat()` 优雅停 bot。Linux docker 环境生效；无 SIGTERM 平台回退到 `KeyboardInterrupt`/atexit（本期 Linux 优先）。

### 4.6 进程退出语义（无参多 channel）

`Gateway.run` 无参分支 `asyncio.gather(*acceptor_tasks)`。**所有 acceptor supervisor task 结束才退进程**：
- wechat 被 stop → wechat supervisor 仍存活（idle）→ 不触发退出，web 继续服务。
- web 崩溃 → web task 结束 → 此时若 wechat supervisor 仍存活，gather 未全部完成，进程不退；需 wechat supervisor 也退出才退。web 崩溃如何带动 wechat supervisor 退出：web task 结束时 gateway 触发 shutdown（`_stop_event.set()` 所有 runtime）→ wechat supervisor 退出 → gather 完成 → 退进程。
- SIGINT → gateway 捕获 → 触发所有 runtime stop + web 退出 → gather 完成。

具体「web 崩溃带动 shutdown」的实现机制在 P2 定（倾向 gateway 监听任一 acceptor task 异常退出 → set 所有 runtime `_stop_event` + cancel web），文档此处只确立语义。

### 4.7 迁移说明

in-process 改造后，P1 产物的 `wechat_admin/server.py` 删除、`lifecycle.py` 简化、`WechatSessionAcceptor`（`session_acceptor.py`）删除。现存手动启动 `--channel_wechat` 仍可用（走 `WechatRuntime(auto_start=True)` 路径）。`channel_admin.sock` 不再产生。已确认接受。

## 5. web_acceptor 集成

### 5.1 router 挂载

`web_acceptor.py`（既有）在 `app.include_router(vault_editor_router)` 之后新增：

```python
from everlingo.gateway.workspace_console.router import router as workspace_console_router
app.include_router(workspace_console_router)
```

### 5.2 API 端点

workspace console router 暴露（前缀 `/api/wechat-channel`），直调 `gateway` 持有的 `WechatRuntime` 实例（经 web_acceptor 既有的 `_gateway` 全局访问 gateway，再经 gateway 暴露的 `wechat_runtime` 属性获取）：

| 方法 | 路径 | 行为 |
|---|---|---|
| GET | `/api/wechat-channel/status` | 调 `runtime.status()` → `{running: bool, state, qr_url, last_error}`。state ∈ SDK 四态 + `stopped`/`conflict` |
| POST | `/api/wechat-channel/start` | 调 `runtime.start_wechat()`（幂等：已 running 返回当前状态；conflict 返回提示） |
| POST | `/api/wechat-channel/stop` | 调 `runtime.stop_wechat()`（写 enable=false） |

### 5.3 静态页 fallback

仿 `/editor`（`web_acceptor.py`）新增 SPA fallback（早于 catch-all `/{path:path}` 注册）：

- `GET /console/me` → `web/dist/me.html`
- `GET /console/web-console`、`GET /console/web-console/{path}` → `web/dist/web-console.html`

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

`web/src/components/ChatWindow.tsx` header（现「笔记编辑器」按钮右侧）加 `Me` 按钮：

```tsx
{!embedded && (
  <div className="flex items-center gap-1">
    <Button variant="ghost" size="sm" onClick={() => { window.location.href = '/editor'; }}>
      <NotebookPen /><span className="hidden md:inline">笔记</span>
    </Button>
    <Button variant="ghost" size="sm" onClick={() => { window.location.href = '/console/me'; }}>
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
| false | stopped | 「Wechat channel 未运行」+ `[启动]` 按钮 |
| true | starting | 「启动中…」+ `[停止]` |
| true | waiting_scan | 「等待扫码」+ `[打开扫码页]`（`window.open(qr_url)` 新 Tab）+ `[停止]` |
| true | scanned | 「已在手机确认，等待登录完成」+ `[停止]` |
| true | logined | 「已登录 ✅」+ `[停止]` |
| — | conflict | 「Wechat 已在 standalone 运行，请先停止该进程」+ `[重试]`（再调 start） |

`last_error` 非空时，UI 顶部红色 banner 显示 message，不阻断当前状态展示与按钮。

### 6.5 无客户端路由

项目不用 react-router（`/editor` 走 `window.location.href` 全页跳转）。`/console/me`、`/console/web-console` 沿用同模式，各自独立 entry。`/console/web-console` 下子页（wechat channel admin）目前单一，无需客户端路由；将来多子项时用 hash 或 query 区分。

### 6.6 Me 页 logout 按钮

`web/src/me/MePage.tsx` 底部（`main` 之后）追加贴底 `footer`，内含全宽 `退出登录` 按钮（`lucide-react` 的 `LogOut` 图标，ghost variant）：

```tsx
<footer className="shrink-0 border-t border-border px-3 py-3 md:px-4">
  <Button
    variant="ghost"
    className="w-full justify-start gap-2 text-muted-foreground"
    onClick={() => { window.location.href = '/logout'; }}
  >
    <LogOut className="size-4" />
    退出登录
  </Button>
</footer>
```

- **跨拓扑行为**：`GET /logout` 是 WS-Router 自有路由（[ws-router.md](../multiple-users/ws-router.md) §4.1），不在后端透传列表内，浏览器请求会先命中 WS-Router → 清 `everlingo_sess` cookie + 302 `/login`。因此仅**多用户部署**（经 WS-Router）下语义成立。
- **单用户本地拓扑**（`python -m everlingo --channel_web`，无 WS-Router）：`web_acceptor.py` 无 `/logout` 路由，点击 404——属预期行为，该拓扑无认证，logout 无意义，不为此加 feature detection 或后端 no-op 路由。

## 7. 自动启动与 enable 持久化

### 7.1 配置模型

`src/everlingo/models.py` 新增：

```python
class ChannelWechat(BaseModel):
    enable: bool = Field(default=False, description="是否启用 wechat channel（重启后自动启动）")

class Channels(BaseModel):
    channel_web: ChannelWeb = Field(default_factory=ChannelWeb, ...)
    channel_wechat: ChannelWechat = Field(default_factory=ChannelWechat, ...)
```

- `channel_wechat` 节点在用户首次经 console 登录成功后由 `on_logined` 回调写入（节点不存在时补写）。
- 节点不存在 = 未启用；节点存在且 `enable: true` = 自动启动；`enable: false` = 用户主动停后不再自动启。

### 7.2 自动启动触发

gateway 无参启动 → `Gateway.run` 读 config → `channel_wechat.enable=true` → 创建 `WechatRuntime(auto_start=True)` → `start()` 内 `_start_wechat()`。因 `credentials.json` 已存（首次登录时 SDK 保存），`bot.login(force=False)` 自动跳过 QR 直接 logined（见 [channel-wechat-ilink.md §分开 login](../channel-wechat-ilink.md)），用户无感知恢复。

### 7.3 enable 写入时机汇总

| 事件 | enable | 触发点 |
|---|---|---|
| console 点「启动」并 login 成功（state→logined） | `true` | `WechatRuntime._on_logined` 回调 `save_setting` |
| console 点「停止」（用户主动停） | `false` | `WechatRuntime.stop_wechat` 内 `save_setting` |
| 重启后自动启动、login 仍成功 | 保持 `true` | 不改 |
| 重启后自动启动、credential 过期需重扫码 | 保持 `true` | 不改（state=waiting_scan，用户扫码后 on_logined 再次写 true） |
| 重启后自动启动、锁冲突（standalone 占用） | 保持 `true` | 不改（status 显示 conflict） |

## 8. 安全与边界

- **默认 localhost**：`plugins.channels.channel_web.listener.interface` 默认 `localhost`，console 仅本机可达。
- **CORS**：`web_acceptor.py` 现有 `allow_origins=["*"]`（[web-session-acceptor.md §CORS](../web-session-acceptor.md)）。console 的 `/api/wechat-channel/*` 同源访问，不受 CORS 影响；但 `allow_origins=["*"]` 意味着任意可达 8000 的网页可调启停接口。公网部署时须收敛白名单 + 加鉴权，本期不做。
- **不暴露 secrets**：runtime / admin_state 只传状态与启停命令，不传 credentials（credentials 由 SDK 自管于 `credentials.json`，见 [channel-wechat-ilink.md §sdk 保存用户 credentials](../channel-wechat-ilink.md)）。
- **进程管理边界**：runtime 只管启停 wechat channel 实例，不介入其聊天消息收发（聊天走既有 Session/WechatChannel 路径，见 [gateway.md](../gateway.md)）。

## 9. 与现有架构的契合

- 复用 `web_acceptor.py` 的 FastAPI app，不新增 server。
- `WechatRuntime` 实现 `SessionAcceptor` 协议，与 `WebSessionAcceptor` 同构，gateway 统一调度。
- 前端复用 [web-chatbot.md](../web-chatbot.md) 技术栈与多入口构建。
- `WechatChannel` 与 `WechatAdminState`（P1 产物）不动，runtime 直接复用。
- config-driven 多 channel 复用既有 `everlingo.yaml` + pydantic 模型 + `save_setting` 范式。
- 不引入新依赖（FastAPI/uvicorn/pydantic/yaml 已在依赖中；前端无新运行时依赖）。

## 10. 扩展位

- `channels` 下将来可加其它 channel 配置节点（如 `channel_telegram`），gateway 无参自动按 config 启动对应 acceptor；console 的 `channels admin` 下可加对应 admin 页。
- `Me` 页预留更多入口（profile、settings 等）。
- runtime 的 `status()` 可扩展更多字段（如 `/logs` 流式日志、`/metrics`），router 加端点即可。
