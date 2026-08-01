## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"

- 2026-08-01 | **Workspace Console — P4（文档收尾 + 单测补全）**：单测核查——P2 单测已全部覆盖（test_runtime / test_lifecycle / test_state / test_router / test_gateway_multichannel 共 42 通过，test_server.py 已删、lifecycle pid 用例已删），**无需补全**。文档校对——channel-wechat-ilink.md（in-process 托管 + on_logined 持久化 + 自动启动）、web-session-acceptor.md（router 挂载 + 静态页 fallback）、gateway.md（config-driven + explicit flag 语义）、user-docs/reference/configuration.md（channel_wechat.enable）均已在 P2/P3 期间同步无缺口。补全唯一缺口：`web-chatbot.md` §Header 与「按钮文字标签自适应隐藏」表记录 `Me` 按钮（header 右侧「笔记编辑器」旁，`window.location.href='/console/me'`，embedded 模式不显示）。phased-impl.md 标记 P4 已完成并修正验证命令路径（`test_gateway_multichannel` → `test_gateway_multichannel.py`）。验证：42 相关用例通过 + `npm run build`（tsc）通过。
- 2026-08-01 | **Workspace Console 路由加 `console/` 前缀，消除与 WS-Router `/me` 冲突**：WS-Router（`ws_router/app.py:144`）与 ws-container（`web_acceptor.py`）曾都注册 `GET /me`（前者 JSON 用户信息、后者 SPA fallback），部署上 WS-Router 先匹配，ws-container 的 `/me` 永不可达。修正：ws-container 的 workspace console 静态页 fallback 加 `console/` 前缀——`web_acceptor.py` `/me`→`/console/me`、`/web-console`、`/web-console/{path}`→`/console/web-console`、`/console/web-console/{path}`；前端同步：`ChatWindow.tsx` header Me 按钮 `'/me'`→`'/console/me'`、`MePage.tsx` 入口 `'/web-console'`→`'/console/web-console'`、`ConsolePage.tsx` `WECHAT_ADMIN_PATH`→`'/console/web-console/plugins/channels/wechat_channel/admin'` 与返回按钮两路径。`npm run build`（tsc + vite）通过并重生成 dist。文档同步：`workspace-console/{architecture,README,phased-impl}.md`、`web-session-acceptor.md`。WS-Router 的 `GET /me` JSON 端点与 `tests/test_ws_router_auth.py` 不变；WS-Router catch-all 自动透传 `/console/*`。验证：`npm run build` 通过、相关 pytest 无回归。
- 2026-07-31 | **Wechat 消息重复（收到两次）修复**：`WechatChannel.init()` 非幂等——`WechatRuntime.start_wechat()`（`wechat_admin/runtime.py:107`）与 `Session.run()`（`session.py:59`）各调一次 `channel.init()`，每次都会创建新的 `WeChatBot` 实例 + 注册消息回调 + 启动独立长轮询线程（`wechat_channel.py`），两个 bot 各自 `get_updates` 收到同一消息并各自 `self._queue.put`，导致 Chat Agent 每条消息处理两次。P1 无此问题（`WechatSessionAcceptor` 依赖 `Session.run()` 单次 init）。修复：`WechatChannel.init()` 加 `_initialized` 幂等守卫（重复调用直接返回）。测试：`test_wechat_channel.py` 新增 `test_init_is_idempotent`（二次 init 不再创建 bot / 线程）。验证：全量 813 通过。
- 2026-07-31 | **Workspace Console — P3（前端三页 + header）**：`web/vite.config.ts` rollupOptions.input 增 `me`、`web-console` entry；新增 `web/me.html`、`web/web-console.html`（仿 editor.html）。新增 `web/src/me/{main.tsx,MePage.tsx}`（Me 页，入口卡片「Workspace Console」→ `/web-console`）；新增 `web/src/web-console/{main.tsx,ConsolePage.tsx,WechatChannelAdmin.tsx,useWechatChannelStatus.ts}`：ConsolePage 按 `location.pathname` 分发（无 react-router，`/web-console/plugins/channels/wechat_channel/admin` 子路径渲染 WechatChannelAdmin，否则频道列表）；`useWechatChannelStatus` 每 2s 轮询 `GET /api/wechat-channel/status`（含 start/stop 调用）；WechatChannelAdmin 按 `running`+`state` 渲染六态 UI（stopped/starting/waiting_scan/scanned/logined/conflict，含「打开扫码页」`window.open(qr_url, "_blank", "noopener")`、last_error 红 banner、conflict 重试）。`ChatWindow.tsx` header「笔记」按钮旁加 `Me` 按钮（`User` 图标，`window.location.href='/me'`，移动端图标常驻文字 `hidden md:inline`）。验证：`npm run build`（tsc + vite）通过，四 entry（index/editor/me/web-console）均产出；端到端走查——gateway 无参启动 → `/me`、`/web-console`、`/web-console/plugins/channels/wechat_channel/admin` 均返回对应 SPA；`POST /api/wechat-channel/start` 真实拉起 SDK 返回 `waiting_scan` + 真实 QR URL；`stop` 写 `enable:false`；SIGTERM 优雅停（no_persist 不改 enable，进程干净退出）。P4（文档收尾 + 单测补全）待做。- 2026-07-31 | **Workspace Console — P2（gateway config-driven 多 channel + WechatRuntime in-process）**：代码实现 + 单测全绿。新增 `wechat_admin/runtime.py` `WechatRuntime`（SessionAcceptor：start 自动启动或 idle、`_supervise` 等 `_stop_event` 后 `stop_wechat(no_persist=True)`、start_wechat 幂等 + acquire_lock 冲突转 `conflict` 态不抛、stop_wechat 写 enable=false、on_logined 回调写 enable=true、`_watch_bot` bot 退出后调 `on_bot_exit`、`request_shutdown` 用于 gateway 信号收尾；`STOP_TIMEOUT=10.0`）。`gateway.py` 重写 `run`/`_build_acceptors`/`_serve`：explicit flag 单 channel（wechat→standalone 带 on_bot_exit；web→WebSessionAcceptor + idle WechatRuntime；stdio→仅 Stdio）、无参 config-driven（`channel_enabled()` 读 `plugins.channels`；web+wechat→双 acceptor、wechat 按 enable 决定 auto_start；均无→回退 stdio）；`_serve` 多 task 用 `asyncio.wait FIRST_COMPLETED` + 收尾（stop_wechat no_persist + timeout + cancel），单 task 且带 wechat_runtime 时注册 SIGINT/SIGTERM 优雅停；`main`/`_parse_args` 支持无参（None）。删 `wechat_admin/server.py`、`session_acceptor.py:WechatSessionAcceptor`，`lifecycle.py` 精简（删 pid，仅保留 acquire_lock/lock_path/LockAcquireError）。`models.py` 加 `ChannelWechat{enable:bool}`，`setting.py` 加 `channel_enabled()`。`wechat_channel.py` 加 `on_logined` 注入回调。新增 `workspace_console/router.py`（`/api/wechat-channel/{status,start,stop}`，经 `web_acceptor._gateway` 访问 `gw.wechat_runtime`，无 gateway/runtime 时 status 返回 stopped、start/stop 503）+ `web_acceptor.py` 挂载 + `/me` `/web-console` 静态 fallback。`entrypoint.sh:35` 改 `python -m everlingo gateway`。测试：新建 `test_runtime.py`（13 项）、`test_gateway_multichannel.py`（7 项）、`workspace_console/test_router.py`（6 项），删 `test_server.py`、精简 `test_lifecycle.py`；修复 async 单测 loop-bound Task 问题（supervise 用例改单 loop 内 `await rt.start()`）。验证：全量 812 通过。P3（前端三页）待做。- 2026-07-31 | **Workspace Console — 设计变更：wechat 由子进程改为 in-process 托管**：原 P1 已实现「wechat gateway 进程内 admin server（UDS）」方案，经评估子进程模型（IPC + 单例锁 + pid 探活 + 信号收尾）维护成本超过收益，改为 **web 进程内 in-process 托管**。决策要点：(1) P1 已把 `bot.run()` 换成 `_run_thread()` + 独立 asyncio loop，asyncio 隔离理由已被消解；(2) 生命周期解耦（web 崩溃 wechat 存活）属性放弃，接受单用户本地场景下 web 崩溃罕见 + credentials.json 免扫码恢复；(3) `--channel_wechat` standalone 入口保留；(4) 删 `wechat_admin/server.py`（UDS admin server），router 直读 `WechatAdminState.snapshot()`；(5) 新增 `everlingo.yaml` 的 `plugins.channels.channel_wechat.enable`，on_logined 回调写 true、stop 写 false，gateway 无参 config-driven 自动恢复 wechat；(6) `entrypoint.sh` 由 `--channel_web` 改无参。文档重写：`docs/impl-spec/workspace-console/{README,architecture,phased-impl}.md`、`docs/impl-spec/gateway.md`（启动模式语义）、`docs/impl-spec/channel-wechat-ilink.md`（in-process 托管节）、`docs/impl-spec/web-session-acceptor.md`（router 挂载）、`user-docs/reference/configuration.md` + `user-docs/deployment/simple-single-deployment.md`（channel_wechat.enable）。P1 产物保留 `state.py`/`lifecycle.py:acquire_lock`/`wechat_channel.py` 改造；删除 `server.py`/pid/`WechatSessionAcceptor` 移到 P2。

- 2026-07-31 | **Workspace Console — P1（wechat gateway 进程内 admin server）**：新增 `src/everlingo/gateway/wechat_admin/`（state.py 线程安全状态机 `WechatAdminState`；lifecycle.py flock 单例锁 + pid 文件；server.py UDS FastAPI `/status` `/last_error` `/shutdown` + `AdminServer` 可优雅关闭）。改造 `wechat_channel.py`：注入 SDK 回调更新状态、启动路径由 `bot.run()` 改为 `_run_thread()`（显式 loop + main task，便于跨线程取消），`_wrap_login()` monkey-patch `bot.login` 注入 `logined`（覆盖首登与 session-expired 重登）、`request_stop()`（stop + 主协程 cancel，解决 QR 等待/长轮询阶段 stop() 不生效）。改造 `session_acceptor.py`：`WechatSessionAcceptor.start` 获取锁 + 写 pid + 并行起 admin server，`_run_until_bot_done` 按「bot 结束 / uvicorn 信号退出」两路径收尾退出进程。`gateway.py` 捕获 `LockAcquireError` 优雅退出。文档 `docs/impl-spec/workspace-console/`（README/architecture/phased-impl）。测试：wechat_admin 22 项 + wechat_channel 新增 8 项，相关 97 测试通过。手工验证：/status（waiting_scan + 真实 QR URL）、/shutdown（2s 退出 + pid 清理）、SIGINT（2s 退出 + pid 清理）、SIGTERM（退出；pid 因 uvicorn 重抛原信号硬终止而残留，web 侧 P2 用 pid 存活校验兜底）、SIGKILL 崩溃后重启（stale socket 被 unlink、锁自动释放）、双实例锁互斥。
- 2026-07-31 | **AdminState 回调调试日志 + stdout/日志文件双输出**：`wechat_admin/state.py` 各状态变更方法（`on_qr_url`/`on_scanned`/`on_expired`/`set_last_error` + `set_state`/`set_qr_url`，日志在锁外输出）加 `info`/`warning` 级调试日志，便于跟踪登录流程（QR 就绪/已扫码/过期/错误/logined）。`log_utils.py:setup_logging()` 追加 stdout `StreamHandler`（与 FileHandler 同 formatter/level），并按 handler 类型幂等去重——重复调用不再叠加同类型 handler（顺带修复潜在重复 FileHandler 隐患）。测试：`test_state.py` 新增 caplog 校验四回调日志；`test_log_utils.py` 新增 stdout handler 与幂等用例。验证：全量 795 通过。
- 2026-07-31 | **Python base image 迁移 bookworm → trixie**：`python:3.12.13-bookworm` → `python:3.12-trixie`。改动：`deploy/deps-base/Dockerfile`（deps/runtime 两 stage base）、`deploy/ws-container/ws-container-spec.md`（3 处 base 描述）、`docs/impl-spec/multiple-users/deploy.md`（ws-router/ws-master 示例 Dockerfile 片段 4 处）。副作用说明——trixie（Debian 13）系统 SQLite 为 3.46.1（bookworm 为 3.40.1），`LIMIT ?` 已支持传给 vec0 xBestIndex；`store.py:_vec0_knn` 仍用 `k = ?`（sqlite-vec 官方推荐写法，两端兼容），仅同步更新 store.py 与 memory-vault-embedding-spec.md 中的注释措辞。ws-container/ws-router/ws-master 三 Dockerfile 均经 `ARG DEPS_IMAGE` 继承，无需改。需重新构建并推送 deps-base 镜像（`everlingo-deps`）到 ghcr 后下游镜像生效。

- 2026-07-30 | **修复 ws-router MasterClient 30s 硬超时导致 browser 过早 503 backend_unavailable**：根因——`master_client.py` 硬编码 `httpx.Timeout(30.0)`，而 `get_default_backend`（router→master 触发 ws-container 创建/启动）在 ws_master 侧可能阻塞长达 `readiness_timeout`（默认 60s，68 慢机器已调至 120s）。router 在 30s 先超时 → `get_default_backend` 返回 None → `catch_all` 回 503 `backend_unavailable`，尽管容器稍后（65s）正常就绪。修复：`RouterConfig` 新增可配字段 `master_timeout: int = 90`（默认 90s，≥ 默认 readiness_timeout 60s + 30s buffer）；`MasterClient.__init__` 接收 `timeout` 参数替代硬编码 30s；`AppState` 传入 `config.master_timeout`。示例配置与 68 env `ws_router.yaml` 同步更新（68 env 设 `master_timeout: 135`，对应当地 `readiness_timeout: 120 + 15s buffer`）。文档 ws-router.md §5 配置表同步。新增测试：`test_ws_router_config.py`（默认值 90 + 自定义 135）、`test_ws_router_master_client.py`（默认 90 / 自定义 / float 转换）。相关测试 15 通过无回归。
- 2026-07-30 | **ws-master idle_timeout 默认值调为 0 及 ws start --user 预热**：文档 ws-master.md 同步 + 代码实现。`config.py` 默认 `idle_timeout=0`；`lifecycle.py` idle 判定加 `if idle_timeout > 0` 守卫；`cli.py` `ws start` 新增 `--user <user_name>`（与 `--id` 互斥），解析 default ws 后同步调用 `lifecycle.ensure_started()` 执行 docker 全流程预热；示例 yaml 与 test fixtures 同步更新；新增 6 项 CLI 测试覆盖完整参数校验。
- 2026-07-30 | **抽离 deps base 镜像，消除源码改动触发 ≈100M .venv 层重下**：根因是 `uv sync` 归零 mtime 差异 + GHA cache 易失导致 `docker pull` 重复下载 100M。新建 `deploy/deps-base/Dockerfile`（pin uv==0.12.0 + mtime 归零 + everlingo user + .venv），三个 Dockerfile 改为 `FROM ${DEPS_IMAGE}`（ARG DEPS_IMAGE 默认 `ghcr.io/labilezhu/everlingo-deps:latest`），CI 新增 `deps-build` → `deps-manifest` → `build`（`needs: deps-build`，传 build-arg DEPS_IMAGE）。源码改动只动 src 层，不复 `uv sync`。文档 CI spec 同步。本地构建改为先 `docker build -f deploy/deps-base/Dockerfile -t everlingo-deps:local .` 再传 `--build-arg DEPS_IMAGE=everlingo-deps:local`。
- 2026-07-30 | 修复 `ws_master.yaml` 的 `image` 字段 `${WORKSPLACE_IMAGE}` 未被 env 展开的 bug（白名单漏 `image`）。改为三处配置（`everlingo.yaml` / `ws_master.yaml` / `ws_router.yaml`）统一使用 `os.path.expandvars` 对所有字符串字段递归展开（支持嵌入式 `${VAR}` / `$VAR`，未设 env 保留字面量 fail-loud）。新增共享工具 `src/everlingo/utils/yaml_env.py:expand_env_vars`。更新 test_ws_master_config.py（移除白名单模式，改 unset env 测试为预期 ValueError）、新建 test_ws_router_config.py（3 项 env 展开测试）、test_setting.py（1 项 everlingo.yaml 展开测试）。文档 ws-master.md §5.1 / ws-router.md §5 同步。
- 2026-07-30 | `public_base_url` scheme 校验：在 `setting.get_web_public_base_url()` 与 `MasterConfig.load()` 中增加 `^https?://` 校验（非 http(s) 开头 raise ValueError），防止配置 typo 静默传播导致 Chat Agent 生成畸形笔记链接。同时添加 trailing slash 剥离、补充 4 项单测（yaml/env 非法 scheme、trailing slash 修剪、ws_master config 非法 scheme），65 相关测试通过无回归。
- 2026-07-29 当前 | **修复 host_ws_dir/container_ws_dir 路径分离**：当 ws-master 容器化时，`host_ws_dir`（docker daemon bind source）与 `container_ws_dir`（容器内文件操作）需分离。新增 `container_ws_dir` 配置字段（默认 `/workspaces`）+ `host_to_container_ws_path()` 前缀转换函数。改动：config.py（字段 + 函数 + env_keys）、lifecycle.py（_create_and_start/remove 文件操作用容器路径，bind source 用宿主路径）、cli.py（_user_rm/_ws_rm rmtree 用容器路径）、yaml 配置、测试（config fixture 分离两路径 + 新增 test_create_bind_source_is_host_path 验证 volumes key=宿主 + 模板落容器路径）。docs/ws-master.md §5.1、deploy.md §4 同步。单测 49 全通过。
- 2026-07-29 当前 | **PR4 — Chrome Extension Token 化**：扩展 Basic Auth → PAT Bearer token。改动：config.ts/OptionsForm/background + 测试随动 + 文档同步。36 测试通过。

- 2026-07-29 | 新增 `cors_allow_origin_regex` 配置字段：允许 WS-Router 通过 regex 匹配 CORS origin，解决 Chrome Extension origin 因扩展 ID 各异无法写死白名单的问题。`config.py` 新增 `cors_allow_origin_regex: str | None`，`app.py` CORSMiddleware 传参 `allow_origin_regex`。`deploy/examples/ws_router.yaml` 注释文档。`test_ws_router_middleware.py` 新增 `TestCORSRegex`（11 → 13 tests）。

- 2026-07-29 | 探活与 backend_url 由容器 hostname 改为容器 IP（`NetworkSettings.Networks[everlingo-net].IPAddress`）——解决本地开发时 ws-master 不在容器内无法解析容器 hostname 的问题。改动：lifecycle.py 新增 `_container_ip()` 读取 docker attrs、`_backend_url` 改为 async 现取 IP 返回 `Optional[str]`（可能为 None）、`_start_and_probe` 内联重试循环每轮刷新 IP、`_probe_with_retry` 移除；测试 mock 容器 attrs 加 IP + URL 断言改为 IP 地址。文档 ws-master.md §3/§6.1/§6.2 与 internal-api-contract.md §2.6/§2.8 同步更新。31 测试通过无回归。
- 2026-07-29 | 修复 `.dockerignore` 与设计文档「docker 按路径就近取用」错误：顶层 `.dockerignore` 排除整个 `web/` 导致 ws-container 无法构建（三 Dockerfile 共用 repo-root build context，Docker 不支持 per-Dockerfile .dockerignore）。改为排除 `web/node_modules/` + `web/dist/`（本地构建产物/临时依赖，ws-container Stage1 在镜像内现场重建），保留 `web/` 其余文件供 ws-container COPY。同步修正 `deploy.md` §5.5 注记、`phases.md` PR3 范围、`TASKS.md` 自身记录。
- 2026-07-29 | 修复 ws-container `public_address.base_url` 透传缺失：ws-master.md 原称「ws-container 经 ws-router 反代无需感知外部域名」有误——Chat Agent 生成笔记 markdown 链接（`<public_address_base_url>/editor?...`，chat-agent-spec.md:145）依赖此值，Web Chatbot `/editor` 跳转与 Chrome Extension 点笔记链接均依赖。改为 WS-Master 把 `ws_master.yaml` 的 `public_base_url` 经容器 env `EVERLINGO_PUBLIC_BASE_URL` 注入 ws-container，`setting.get_web_public_base_url()` 新增 env fallback（优先级：yaml 显式 > env > listener 自动生成）。同步把 `ws_router.yaml` 的 `base_url` 字段改名为 `public_base_url` 统一命名（原字段无任何代码使用点，纯文档/配置声明）。改动：config.py（MasterConfig+RouterConfig 加/改名 public_base_url + env 展开）、lifecycle.py（create env 注入）、setting.py（env fallback）；文档 ws-master.md §5.1/§5.2/§6.2/§10、ws-router.md §5、ws_container_everlingo_template.yaml 注释、deploy/examples 三个示例配置；新测试 test_ws_master_config.py 4 项 + test_setting.py 2 项 env fallback + test_ws_master_lifecycle.py 1 项 env 注入，全量相关测试通过无回归。
- 2026-07-29 | 修复 `docker.containers.create()` 不支持 `network_aliases` kwarg 导致的容器创建失败：docker-py 7.2.0 的 `create()` 不接受 `network_aliases`（那是 `run()` 的别名参数），改为 `networking_config={network: {"Aliases": [container_name]}}` 实现同语义。更新 `src/everlingo/ws_master/lifecycle.py:152-172`，补 tests `test_ws_master_lifecycle.py` 两项 `networking_config` / 无 `network_aliases` 断言，10 测试通过无回归。

- 2026-07-29 | ws-router/ws-master 日志修复：1) 两 daemon 的 `run_daemon` 加 `logging.basicConfig(level=INFO)`，解锁全部现有 `logger.info/warning` 调用（21 处 lifecycle、master_client 4 处 network-error warning）；2) `MasterClient` 四个方法（authenticate/pat_verify/get_user/get_default_backend）加 non-200 的 `logger.warning`，静默 `return None` 不再静默；3) `post_login` 失败时加 `logger.warning`（含 username 与 client IP），直接定位 401 根因。`basicConfig` 放函数内，测试调 `create_app` 不触发，78 测试无回归。
- 2026-07-29 当前 | **PR3 — 部署编排**：完整实现部署拓扑。
  - `docker-compose.yml` 落地于仓库根，含 ws_router / ws_master 两个服务 + everlingo-net + master-data volume。
  - `deploy/ws-router/Dockerfile` 与 `deploy/ws-master/Dockerfile` 更新：`ENTRYPOINT` 改为 `["python","-m","everlingo"]`（子命令与 `--config` 由 compose `command:` 提供）；deps stage 补 `HTTP_PROXY`/`HTTPS_PROXY` build-arg。
  - 示例配置文件落地：`deploy/examples/ws_router.yaml`、`deploy/examples/ws_master.yaml`、`deploy/examples/ws_container_everlingo_template.yaml`。
  - 外部 nginx 配置示例落地：`deploy/nginx/everlingo.conf.example`。
  - `.dockerignore` 新增于仓库根，排除 ws-router/ws-master 构建无关的大目录（排除 `web/node_modules/` + `web/dist/` 而非整个 `web/`，因 ws-container 与 ws-router/ws-master 共用同一 repo-root build context）。
  - 设计文档同步：deploy.md（§2 compose command/ENTRYPOINT 拆分、§5.2/§5.3 Dockerfile 更新、新增 §5.4 示例配置布局、§5.5 .dockerignore）、external-nginx.md（§3 加落地路径注记）、phases.md（PR3 范围补全）。
- 2026-07-29 | WS-Router / WS-Master Dockerfile 落盘到独立目录：新建 `deploy/ws-router/Dockerfile` 与 `deploy/ws-master/Dockerfile`（内容取自 deploy.md §5.2/§5.3 精简构建 sketch：deps + runtime 两 stage，跳过 frontend-builder，无 `web/dist`，仅加头部构建命令注释）。原设计文档路径 `deploy/ws-container/Dockerfile.ws_router` / `Dockerfile.ws_master` 从未落盘，本次为首次创建。路径引用同步更新：deploy.md（§5.2 标题 / §5.3 标题 / §6 两条 buildx 命令）、ws-master.md §9、ws-router.md §6、phases.md PR3 范围两条。archived-task.md 为历史快照未改。遗留待定：compose `command:` 与镜像 `ENTRYPOINT` 重复参数矛盾（PR3 落地时统一）；是否补 `HTTP_PROXY` build-arg（与现有 ws-container Dockerfile 对齐）待确认。
- 2026-07-29 | 部署目录重组：`docs/impl-spec/deploy` → 顶层 `deploy/`，`docs/impl-spec/deploy/image` → `deploy/ws-container/`。全局引用更新：ARCHITECTURE.md、CI spec、multiple-users 下所有文档、web_acceptor.py 与 test_web_acceptor.py 的 ref 注释、TASKS.md。docs/archived/archived-task.md 为历史快照未改。
- 2026-07-29 | 执行 `mark-specific/local-deploy/130_deploy/130-everlingo-nginx.md` 部署计划：§3.1 签发 TLS 证书（acme.sh dns_ali 成功签发 `home130-everlingo.mygraphql.com`）；§3.3+§3.4 新建 site 配置并启用；§4 验证通过（TLSv1.3 握手成功，nginx 正确透传到上游）。
- 2026-07-29 | 完善 130-everlingo-nginx.md（公网 nginx TLS 反代到 `.130:8100` ws-router 的本地测试计划）：§2.2 改写 TLS terminate + 明文 HTTP proxy_pass 跨机透传；§2.3 SSE 长连接指令表；§2.4 trusted_proxy 跨机注意事项；§3.3 补全完整 server block 配置；同步更新 external-nginx.md §5。
- 2026-07-29 当前 | **PR2 — WS-Router 模块**：完整实现前台反代 + 认证服务。配置加载、缓存工具、Master 客户端、认证模块（PasswordAuthProvider + JWT HS256）、auth_middleware（四路径认证）、反向代理（SSE 流式透传）、FastAPI 应用（含 CORS）。入口更新（main.py ws_router 子命令）。30 个新测试用例，全量 726 测试通过无回归。
- 2026-07-29 当前 | **PR1 — WS-Master 模块**：完整实现三层架构。数据层（config/db/repo/pat_utils）、CLI 层（user/pat/ws/identity 子命令）、Internal API + 容器生命周期（FastAPI 9 端点 + docker SDK 状态机 + 并发控制 + idle timeout + 启动对账）。入口更新。75 个新测试用例，全量 696 测试通过无回归。
- 2026-07-29 当前 | **PR0 — 依赖与骨架**：审批通过 `docker>=7.0` 与 `pyjwt>=2.8`。空包骨架（ws_router/ + ws_master/ + __main__.py 占位）。main.py 子命令注册。10 个测试用例，全量 621 测试通过。
- 2026-07-27 21:56 | Envelope 重构：`selection` + `context` 替换为 `chat_context.resource_contexts[]`（tagged union: vault_file / web_page / selected_text）。
- 2026-07-27 17:00 | 拆分 `source.kind`：Chrome Extension 由 `web` 改为 `chrome_ext`。
- 2026-07-27 当前 | 修复 Source 模式编辑器失焦后选区高亮消失（CM6 drawSelection 扩展）。
- 2026-07-27 当前 | 修复 WYSIWYG 模式编辑器失焦后选区高亮消失（ghostSelectionPlugin）。
- 2026-07-28 | 多用户部署：per-user container 路线设计文档。
- 2026-07-29 | 多用户部署设计修订：引入 ws-container 一等概念，重命名 edge→ws_router / master→ws_master。
- 2026-07-29 | Dockerfile 加 HEALTHCHECK + ws-container-spec.md 同步。
- 2026-07-29 | 实现 `/healthz` 端点（web_acceptor.py 4 用例）。
- 2026-07-29 | ws-container 健康检查端点设计 + 文件重命名（container-spec.md → ws-container-spec.md）。
- 2026-07-29 | 新增分阶段实现计划 phases.md（PR0~PR4）。
- 2026-07-29 | 新增 Internal API 契约文档 internal-api-contract.md。
- 2026-07-29 | 多 SSO provider 支持：user_identities 表设计。

- 2026-07-29 | 探活与 backend_url 由容器 hostname 改为容器 IP（`NetworkSettings.Networks[everlingo-net].IPAddress`）——解决本地开发时 ws-master 不在容器内无法解析容器 hostname 的问题。改动：lifecycle.py 新增 `_container_ip()` 读取 docker attrs、`_backend_url` 改为 async 现取 IP 返回 `Optional[str]`（可能为 None）、`_start_and_probe` 内联重试循环每轮刷新 IP、`_probe_with_retry` 移除；测试 mock 容器 attrs 加 IP + URL 断言改为 IP 地址。文档 ws-master.md §3/§6.1/§6.2 与 internal-api-contract.md §2.6/§2.8 同步更新。31 测试通过无回归。
- 2026-07-29 | 修复 `.dockerignore` 与设计文档「docker 按路径就近取用」错误：顶层 `.dockerignore` 排除整个 `web/` 导致 ws-container 无法构建（三 Dockerfile 共用 repo-root build context，Docker 不支持 per-Dockerfile .dockerignore）。改为排除 `web/node_modules/` + `web/dist/`（本地构建产物/临时依赖，ws-container Stage1 在镜像内现场重建），保留 `web/` 其余文件供 ws-container COPY。同步修正 `deploy.md` §5.5 注记、`phases.md` PR3 范围、`TASKS.md` 自身记录。
- 2026-07-29 | 修复 ws-container `public_address.base_url` 透传缺失：ws-master.md 原称「ws-container 经 ws-router 反代无需感知外部域名」有误——Chat Agent 生成笔记 markdown 链接（`<public_address_base_url>/editor?...`，chat-agent-spec.md:145）依赖此值，Web Chatbot `/editor` 跳转与 Chrome Extension 点笔记链接均依赖。改为 WS-Master 把 `ws_master.yaml` 的 `public_base_url` 经容器 env `EVERLINGO_PUBLIC_BASE_URL` 注入 ws-container，`setting.get_web_public_base_url()` 新增 env fallback（优先级：yaml 显式 > env > listener 自动生成）。同步把 `ws_router.yaml` 的 `base_url` 字段改名为 `public_base_url` 统一命名（原字段无任何代码使用点，纯文档/配置声明）。改动：config.py（MasterConfig+RouterConfig 加/改名 public_base_url + env 展开）、lifecycle.py（create env 注入）、setting.py（env fallback）；文档 ws-master.md §5.1/§5.2/§6.2/§10、ws-router.md §5、ws_container_everlingo_template.yaml 注释、deploy/examples 三个示例配置；新测试 test_ws_master_config.py 4 项 + test_setting.py 2 项 env fallback + test_ws_master_lifecycle.py 1 项 env 注入，全量相关测试通过无回归。
- 2026-07-29 | 修复 `docker.containers.create()` 不支持 `network_aliases` kwarg 导致的容器创建失败：docker-py 7.2.0 的 `create()` 不接受 `network_aliases`（那是 `run()` 的别名参数），改为 `networking_config={network: {"Aliases": [container_name]}}` 实现同语义。更新 `src/everlingo/ws_master/lifecycle.py:152-172`，补 tests `test_ws_master_lifecycle.py` 两项 `networking_config` / 无 `network_aliases` 断言，10 测试通过无回归。

- 2026-07-29 当前 | **PR4 — Chrome Extension Token 化**：替换 Basic Auth 为 PAT Bearer token。`extension/src/config.ts` 移除 Basic Auth（`SERVER_USERNAME_STORAGE_KEY`/`SERVER_PASSWORD_STORAGE_KEY`/`getApiAuth`/`buildBasicAuthHeader`），新增 `SERVER_TOKEN_STORAGE_KEY`/`getApiToken`/`buildBearerHeader`；`getApiConfig()` 形状不变，5 个调用点零改动。`OptionsForm.tsx` 用户名/密码两字段 → 单一 Token 字段，直连裸 ws-container 留空不认证。`background.ts` `onInstalled` 清旧凭据。`config.test.ts` 与 `sseClient.test.ts` 更新为 Bearer fixture。36 测试通过无回归。phases.md 同步状态表与 PR4 范围。

- 2026-07-29 | ws-router/ws-master 日志修复：1) 两 daemon 的 `run_daemon` 加 `logging.basicConfig(level=INFO)`，解锁全部现有 `logger.info/warning` 调用（21 处 lifecycle、master_client 4 处 network-error warning）；2) `MasterClient` 四个方法（authenticate/pat_verify/get_user/get_default_backend）加 non-200 的 `logger.warning`，静默 `return None` 不再静默；3) `post_login` 失败时加 `logger.warning`（含 username 与 client IP），直接定位 401 根因。`basicConfig` 放函数内，测试调 `create_app` 不触发，78 测试无回归。
- 2026-07-29 当前 | **PR3 — 部署编排**：完整实现部署拓扑。
  - `docker-compose.yml` 落地于仓库根，含 ws_router / ws_master 两个服务 + everlingo-net + master-data volume。
  - `deploy/ws-router/Dockerfile` 与 `deploy/ws-master/Dockerfile` 更新：`ENTRYPOINT` 改为 `["python","-m","everlingo"]`（子命令与 `--config` 由 compose `command:` 提供）；deps stage 补 `HTTP_PROXY`/`HTTPS_PROXY` build-arg。
  - 示例配置文件落地：`deploy/examples/ws_router.yaml`、`deploy/examples/ws_master.yaml`、`deploy/examples/ws_container_everlingo_template.yaml`。
  - 外部 nginx 配置示例落地：`deploy/nginx/everlingo.conf.example`。
  - `.dockerignore` 新增于仓库根，排除 ws-router/ws-master 构建无关的大目录（排除 `web/node_modules/` + `web/dist/` 而非整个 `web/`，因 ws-container 与 ws-router/ws-master 共用同一 repo-root build context）。
  - 设计文档同步：deploy.md（§2 compose command/ENTRYPOINT 拆分、§5.2/§5.3 Dockerfile 更新、新增 §5.4 示例配置布局、§5.5 .dockerignore）、external-nginx.md（§3 加落地路径注记）、phases.md（PR3 范围补全）。
- 2026-07-29 | WS-Router / WS-Master Dockerfile 落盘到独立目录：新建 `deploy/ws-router/Dockerfile` 与 `deploy/ws-master/Dockerfile`（内容取自 deploy.md §5.2/§5.3 精简构建 sketch：deps + runtime 两 stage，跳过 frontend-builder，无 `web/dist`，仅加头部构建命令注释）。原设计文档路径 `deploy/ws-container/Dockerfile.ws_router` / `Dockerfile.ws_master` 从未落盘，本次为首次创建。路径引用同步更新：deploy.md（§5.2 标题 / §5.3 标题 / §6 两条 buildx 命令）、ws-master.md §9、ws-router.md §6、phases.md PR3 范围两条。archived-task.md 为历史快照未改。遗留待定：compose `command:` 与镜像 `ENTRYPOINT` 重复参数矛盾（PR3 落地时统一）；是否补 `HTTP_PROXY` build-arg（与现有 ws-container Dockerfile 对齐）待确认。
- 2026-07-29 | 部署目录重组：`docs/impl-spec/deploy` → 顶层 `deploy/`，`docs/impl-spec/deploy/image` → `deploy/ws-container/`。全局引用更新：ARCHITECTURE.md、CI spec、multiple-users 下所有文档、web_acceptor.py 与 test_web_acceptor.py 的 ref 注释、TASKS.md。docs/archived/archived-task.md 为历史快照未改。
- 2026-07-29 | 执行 `mark-specific/local-deploy/130_deploy/130-everlingo-nginx.md` 部署计划：§3.1 签发 TLS 证书（acme.sh dns_ali 成功签发 `home130-everlingo.mygraphql.com`）；§3.3+§3.4 新建 site 配置并启用；§4 验证通过（TLSv1.3 握手成功，nginx 正确透传到上游）。
- 2026-07-29 | 完善 130-everlingo-nginx.md（公网 nginx TLS 反代到 `.130:8100` ws-router 的本地测试计划）：§2.2 改写 TLS terminate + 明文 HTTP proxy_pass 跨机透传；§2.3 SSE 长连接指令表；§2.4 trusted_proxy 跨机注意事项；§3.3 补全完整 server block 配置；同步更新 external-nginx.md §5。
- 2026-07-29 当前 | **PR2 — WS-Router 模块**：完整实现前台反代 + 认证服务。配置加载、缓存工具、Master 客户端、认证模块（PasswordAuthProvider + JWT HS256）、auth_middleware（四路径认证）、反向代理（SSE 流式透传）、FastAPI 应用（含 CORS）。入口更新（main.py ws_router 子命令）。30 个新测试用例，全量 726 测试通过无回归。
- 2026-07-29 当前 | **PR1 — WS-Master 模块**：完整实现三层架构。数据层（config/db/repo/pat_utils）、CLI 层（user/pat/ws/identity 子命令）、Internal API + 容器生命周期（FastAPI 9 端点 + docker SDK 状态机 + 并发控制 + idle timeout + 启动对账）。入口更新。75 个新测试用例，全量 696 测试通过无回归。
- 2026-07-29 当前 | **PR0 — 依赖与骨架**：审批通过 `docker>=7.0` 与 `pyjwt>=2.8`。空包骨架（ws_router/ + ws_master/ + __main__.py 占位）。main.py 子命令注册。10 个测试用例，全量 621 测试通过。
- 2026-07-27 21:56 | Envelope 重构：`selection` + `context` 替换为 `chat_context.resource_contexts[]`（tagged union: vault_file / web_page / selected_text）。
- 2026-07-27 17:00 | 拆分 `source.kind`：Chrome Extension 由 `web` 改为 `chrome_ext`。
- 2026-07-27 当前 | 修复 Source 模式编辑器失焦后选区高亮消失（CM6 drawSelection 扩展）。
- 2026-07-27 当前 | 修复 WYSIWYG 模式编辑器失焦后选区高亮消失（ghostSelectionPlugin）。
- 2026-07-28 | 多用户部署：per-user container 路线设计文档。
- 2026-07-29 | 多用户部署设计修订：引入 ws-container 一等概念，重命名 edge→ws_router / master→ws_master。
- 2026-07-29 | Dockerfile 加 HEALTHCHECK + ws-container-spec.md 同步。
- 2026-07-29 | 实现 `/healthz` 端点（web_acceptor.py 4 用例）。
- 2026-07-29 | ws-container 健康检查端点设计 + 文件重命名（container-spec.md → ws-container-spec.md）。
- 2026-07-29 | 新增分阶段实现计划 phases.md（PR0~PR4）。
- 2026-07-29 | 新增 Internal API 契约文档 internal-api-contract.md。
- 2026-07-29 | 多 SSO provider 支持：user_identities 表设计。
- 2026-07-29 | WS-Router / WS-Master Dockerfile 落盘到独立目录：新建 `deploy/ws-router/Dockerfile` 与 `deploy/ws-master/Dockerfile`（内容取自 deploy.md §5.2/§5.3 精简构建 sketch：deps + runtime 两 stage，跳过 frontend-builder，无 `web/dist`，仅加头部构建命令注释）。原设计文档路径 `deploy/ws-container/Dockerfile.ws_router` / `Dockerfile.ws_master` 从未落盘，本次为首次创建。路径引用同步更新：deploy.md（§5.2 标题 / §5.3 标题 / §6 两条 buildx 命令）、ws-master.md §9、ws-router.md §6、phases.md PR3 范围两条。archived-task.md 为历史快照未改。遗留待定：compose `command:` 与镜像 `ENTRYPOINT` 重复参数矛盾（PR3 落地时统一）；是否补 `HTTP_PROXY` build-arg（与现有 ws-container Dockerfile 对齐）待确认。
- 2026-07-29 | 部署目录重组：`docs/impl-spec/deploy` → 顶层 `deploy/`，`docs/impl-spec/deploy/image` → `deploy/ws-container/`。全局引用更新：ARCHITECTURE.md、CI spec、multiple-users 下所有文档、web_acceptor.py 与 test_web_acceptor.py 的 ref 注释、TASKS.md。docs/archived/archived-task.md 为历史快照未改。

- 2026-07-29 | 执行 `mark-specific/local-deploy/130_deploy/130-everlingo-nginx.md` 部署计划：
  - §3.1 签发 TLS 证书：acme.sh dns_ali 成功签发 `home130-everlingo.mygraphql.com`，`--installcert` 到 `/etc/nginx/cert.d/`，`--reloadcmd` 触发 `nginx -s reload`。
  - §3.3+§3.4 新建 site 配置并启用：`/etc/nginx/sites-available/home130-everlingo` 写入完整 server block（6457 ssl IPv4+IPv6、SSE 配置、proxy_pass http://192.168.16.130:8100），`ln -s` 启用，`nginx -t` 通过，`systemctl reload nginx` 成功。
  - §4 验证：在 `.130:8100` mock HTTP server，curl `https://home130-everlingo.mygraphql.com:6457/` 返回 `200 Hello from ws-router mock`。TLSv1.3 握手成功，证书验证通过，nginx 正确透传到上游。
- 2026-07-29 | 完善 `mark-specific/local-deploy/130_deploy/130-everlingo-nginx.md`（公网 nginx TLS 反代到 `.130:8100` ws-router 的本地测试计划）：
  - §2.2 改写为「TLS terminate + 明文 HTTP `proxy_pass` 跨机透传，nginx 不做 HTTP 层业务逻辑（无认证/无分流/无缓冲）」，消除原「不处理 HTTP 协议」与「转发明文 HTTP」的自相矛盾，并点明与 `external-nginx.md` 同宿主假设的差异（`proxy_pass http://192.168.16.130:8100`）。
  - 新增 §2.3「SSE 长连接 / 无 buffer」指令表（`proxy_buffering off` / `proxy_cache off` / `proxy_read/send_timeout 3600s` / `proxy_http_version 1.1` + `Connection ""`），与 `external-nginx.md` §4 对齐；标注当前仅 SSE、不设 WebSocket `Upgrade` 头。
  - 新增 §2.4「trusted_proxy 跨机注意」（展开为 §2.4.1~2.4.3 三小节）：§2.4.1 解释 trusted_proxy 逻辑——只采信白名单内来源 IP 的 `X-Forwarded-Proto`，防客户端伪造；该头决定 cookie `Secure` 位。§2.4.2 说明跨机场景的坑：照搬 `ws-router.md` §5 范例的 `trusted_proxy: 127.0.0.1`（同宿主前提）会导致 nginx(.68)→ws-router(.130) 来源 IP 不匹配，ws-router 忽略 `X-Forwarded-Proto`、cookie 不带 Secure、重定向/base_url 错用 `http://`。§2.4.3 给出正确配置 `trusted_proxy: 192.168.16.68`（nginx 出站 IP）。
  - §3.3 补全完整 `server` block 配置（`listen 6457 ssl` IPv4+IPv6、`ssl_certificate*`、`X-Forwarded-Proto $scheme`、`proxy_pass_request_headers on` 透传 `Authorization: Bearer`、SSE 指令、`location / proxy_pass http://192.168.16.130:8100`），附逐项对应 ws-router/external-nginx 章节的设计注解。
  - 同步更新设计文档 `docs/impl-spec/multiple-users/external-nginx.md` §5：明确「nginx 与 ws-router 跨机时 `trusted_proxy` 必须配为 nginx 出站 IP（非 127.0.0.1）」，并给出 `.68/.130` 示例，避免读者照搬同宿主范例导致 cookie Secure 失效。
- 2026-07-29 当前 | **PR2 — WS-Router 模块**：完整实现前台反代 + 认证服务。
  - **配置加载**：`ws_router/config.py`（`RouterConfig` dataclass，YAML 加载，零外依赖）。
  - **缓存工具**：`ws_router/cache.py`（`TTLCache` LRU+TTL，用于 PAT verify / backend URL / /me 缓存）。
  - **Master 客户端**：`ws_router/master_client.py`（`MasterClient` 封装 WS-Master Internal API 调用：authenticate、pat_verify、get_user、get_default_backend）。
  - **认证模块**：`ws_router/auth.py`（`AuthProvider` Protocol + `PasswordAuthProvider`，JWT HS256 签发/验签，TTL 8h，内联登录页 HTML）。
  - **中间件**：`ws_router/middleware.py`（`auth_middleware` 实现 Bearer→JWT→PAT→Cookie 四路径认证，浏览器 302 `/login` / 程序化 401 分流）。
  - **反向代理**：`ws_router/proxy.py`（httpx 反代 + SSE `client.stream()` 流式透传，hop-by-hop 头剔除，`X-Everlingo-User` 注入）。
  - **FastAPI 应用**：`ws_router/app.py`（`AppState` + `create_app` + 路由：`GET/POST /login` 表单/JSON 双格式、`GET /logout`、`GET /me` 带缓存、`GET /healthz`、catch-all `/{path:path}` 反代 + CORS 中间件）。
  - **入口更新**：`main.py` ws_router 子命令支持 `--config` daemon 模式；`ws_router/__main__.py` daemon 入口。
  - **测试**：30 个新测试用例（JWT 5 + login 5 + logout 1 + /me 3 + auth_middleware 8 + CORS 2 + proxy 5 + backend 2），全量 726 测试通过无回归。
- 2026-07-29 当前 | **PR1 — WS-Master 模块**：完整实现三层架构。
  - **数据层**：`config.py`（Pydantic dataclass 读 `ws_master.yaml` + env 展开 `${VAR}`）、`db.py`（四张表幂等建表 + WAL + foreign_keys + check_same_thread=False）、`repo.py`（UserRepo/PatRepo/WsContainerRepo/IdentityRepo 纯 CRUD + 约束）、`pat_utils.py`（`elpat_<base62>` 生成 + sha256 哈希）。
  - **CLI 层**：`cli.py`（`user add/list/rm`、`pat add/list/rm`、`ws add/list/rm/start/stop/set-default`、`identity list/unlink`，直连 sqlite，`user add` 同步创建 default ws-container status=absent）。密码用 PBKDF2-SHA256（stdlib，零外依赖）。
  - **Internal API + 容器生命周期**：`app.py`（FastAPI 监听 8101，X-Master-Token 中间件，9 个 Internal API 端点全部实现：authenticate/pat/verify/pat/users/{id}/users/{id}/ws/users/{id}/default-ws/backend/ws/{id}/backend/ws/{id}/ensure_started/healthz）、`lifecycle.py`（docker SDK 状态机 absent→creating→starting→started，per-ws asyncio.Lock + in-flight 结果复用，httpx 探活轮询，readiness_timeout 超时兜底，启动对账 reconcile，idle timeout 后台 healthcheck_loop）。
  - **入口更新**：`main.py` ws_master 子命令支持 `--config` daemon 模式 + `user/pat/ws/identity` CLI 子命令；`ws_master/__main__.py` 支持两种入口。
  - **测试**：75 个新测试用例（数据层 6 + CRUD 22 + CLI 15 + 生命周期 9 + API 23），全量 696 测试通过无回归。
- 2026-07-29 当前 | **PR0 — 依赖与骨架**：审批通过 `docker>=7.0` 与 `pyjwt>=2.8` 两个依赖。`pyproject.toml` 新增依赖；新建 `src/everlingo/ws_router/` 与 `src/everlingo/ws_master/` 空包骨架（`__init__.py` + `__main__.py` 占位）；`main.py` 新增 `ws_router` / `ws_master` 子命令注册与 stub dispatch（`--help` 可用，不启动服务）；新增 `tests/test_multiuser_cli.py`（10 个用例：主 help 列子命令 / 子命令 help 退出码 0 / 子命令可 import）。`uv sync` 成功，全量 621 测试通过无回归。
- 2026-07-27 21:56 | Envelope 重构：`selection` + `context` 替换为 `chat_context.resource_contexts[]`（tagged union: `vault_file` / `web_page` / `selected_text`）。涉及文件：envelope.py（新增 ChatContextPart、三种 ResourceContext，删 SelectionPart/ContextPart/ScreenshotPart）；test_envelope.py（重写，新增 ChatContext / ResourceContextTaggedUnion 测试）；envelope_spec.md（重写 schema、示例）；agent.py（延续规则改为基于 resource_contexts 判空）；extension 端 extract.ts/envelope.ts/envelope.test.ts/ChatWindow.tsx（重构为 selected_text 结构）；web 端 types/chat.ts/sseClient.ts/ChatWindow.tsx（新增 resourceContextProvider 机制）；EditorApp.tsx/MilkdownEditor.tsx/SourceEditor.tsx（editorSelectionRef 获取编辑器选区实现上下文注入）；envelope-impl-spec.md 同步。
- 2026-07-27 17:00 | 拆分 `source.kind`：Chrome Extension 由 `web` 改为 `chrome_ext`，与 Standalone Web Chatbot 的 `web` 区分。涉及文件：envelope.py（新增 SourceChromeExt、收窄 SourceWeb.surface 为 fullscreen）；test_envelope.py（SourceChromeExt 测试 + surface 校验更新）；envelope_spec.md（kind 表格 + chrome_ext 节 + 示例）；extension types/envelope.ts + test（kind/类型/buildEnvelope）；文档同步（chrome-extension-spec.md / chrome-extension-impl-spec.md / envelope-impl-spec.md / web-session-acceptor.md）
- 2026-07-27 当前 | 修复 Source 模式编辑器失焦后选区高亮消失：SourceEditor.tsx 添加 CM6 `drawSelection()` 扩展，使选区高亮在点击 chatbot 侧栏后仍可见。文档同步 vault-editor.md §编辑器上下文注入。
- 2026-07-27 当前 | 修复 WYSIWYG 模式编辑器失焦后选区高亮消失：新增 `ghostSelectionPlugin.ts`（基于 ProseMirror Decoration + focus-tracking 的幽灵选区插件），接入 Milkdown 编辑器。文档同步 vault-editor.md §编辑器上下文注入。
- 2026-07-28 | 多用户部署：per-user container 路线设计文档（取代 planning-discuss.md 的进程内多 workspace 路线）。新增文档：`docs/impl-spec/multiple-users/edge.md`（Edge 服务：认证 + 反代）、`everlingo-master.md`（Master 服务：用户容器生命周期 + sqlite 数据所有者）、`external-nginx.md`（宿主现有 nginx 反代配置，含 SSE 长连接）、`deploy.md`（全容器化拓扑 + docker-compose + Dockerfile.edge/Dockerfile.master）；更新 `app-entry.md`（加 edge/master 两个进程入口）。待实现：PR1 Master 模块（docker SDK + internal API + CLI）、PR2 Edge 模块（auth 中间件 + httpx 反代含 SSE 透传 + master_client）、PR3 部署编排（compose + 外部 nginx 配置 + Dockerfile.edge/master）、PR4 Chrome Extension Token 化（替换 Basic Auth）。新增依赖（待批准写入 pyproject.toml）：`docker>=7.0`、`pyjwt>=2.8`。
- 2026-07-29 | 多用户部署设计修订：引入 `workspace container`（ws-container）一等概念，把容器生命周期与 user 身份解耦，支持未来单 user 多 ws。重命名：`edge`→`ws_router`、`master`→`ws_master`（CLI 子命令 + 源码包 `src/everlingo/ws_router/`、`ws_master/` + 配置 `ws_router.yaml`/`ws_master.yaml` + DB `ws_master.sqlite` + 镜像 `everlingo-ws-router`/`everlingo-ws-master` + Dockerfile `Dockerfile.ws_router`/`Dockerfile.ws_master`）；文档文件 `everlingo-master.md`→`ws-master.md`、`edge.md`→`ws-router.md`（git mv）。数据模型：`containers` 表→`ws_containers` 表（PK 改 `ws_container_id`，新增 `is_default`/`docker_container_id`/`host_workspace_dir`/`error_message`，删 `users.workspace_dir`）；`users` 表新增 nullable `openai_*` 四字段（远期 per-user key 预留）。状态机：`absent/creating/starting/started/stopped/error` + 并发控制（per-ws asyncio.Lock）+ WS-Master 启动对账。配置拆分：LLM 配置留 `ws_master.yaml`（容器 env 注入，不落盘），新增 `ws_container_everlingo_template.yaml`（openai_* 留空 env fallback，language 默认值可覆盖）。API 多 ws 形状：`GET /internal/users/{uid}/ws`、`GET /internal/ws/{id}/backend`、便捷端点 `GET /internal/users/{uid}/default-ws/backend`（Phase 1 ws-router 实用）；删 `GET /internal/users/{uid}/backend`。容器名 `everlingo-<user_name>-<short_id>`；目录 `<host_ws_dir>/<user_name>/<ws_container_id>/`。待实现 PR 更新：PR1 ws_master 模块、PR2 ws_router 模块、PR3 部署编排（Dockerfile.ws_router/ws_master + 模板挂载）、PR4 Chrome Extension Token 化。
- 2026-07-29 | Dockerfile 加 HEALTHCHECK + ws-container-spec.md 同步：`docs/impl-spec/deploy/image/Dockerfile` 新增 `HEALTHCHECK` 指令（`--interval=30s --timeout=5s --start-period=60s --retries=3`，CMD 用 python urllib 探 `http://127.0.0.1:8000/healthz`）。`start-period=60s` 覆盖 indexer 冷启（unidic-lite 词典加载 + sqlite 初始化）避免误判 unhealthy。`ws-container-spec.md` healthz 节从「计划新增」语气改为「已实现」：动机段改过去时；端点响应补 503 体 `{"status":"error","reason":"gateway_not_initialized"|"indexer_not_ready"}`；新增「就绪判定」条件（`_gateway` 注入 + `indexer.mcp.url` 存在）与「不校验项」（不做 TCP 端口探测/不校验 LLM 可达性）两小节；Dockerfile HEALTHCHECK 节从「可选」改为「已配置」、示例 start-period 30s→60s、补 interval/retries 说明与单用户自愈场景。
- 2026-07-29 | 实现 `/healthz` 端点：`src/everlingo/gateway/web_acceptor.py` 新增 `GET /healthz`（注册在 catch-all `/{path:path}` 之前）。就绪判定（本地同步、无网络 IO）：`_gateway is None` → 503 `gateway_not_initialized`；`indexer.mcp.url` 文件不存在 → 503 `indexer_not_ready`；否则 200 `{"status":"ok"}`。不做 TCP 端口探测（entrypoint.sh 已保证启动时 indexer 端口通，运行中崩溃由 WS-Master healthcheck task 兜底）与 LLM 可达性校验（请求时按需失败重试）。新增依赖导入 `JSONResponse` 与 `indexer_mcp_url_path`。测试 `tests/test_web_acceptor.py::TestHealthz` 4 个用例：就绪 200 / gateway 未初始化 503 / indexer 未就绪 503 / 路由顺序在 catch-all 之前。全量 23 测试通过无回归。
- 2026-07-29 | ws-container 健康检查端点设计 + 文件重命名：发现现有 workspace container 对外无 health check（entrypoint.sh 仅做容器内 indexer→gateway 顺序探测，web_acceptor.py 无 /healthz 端点），WS-Master lazy start 状态机 §6.1/§7 依赖「探活通过」无从实现。决策方案 A：gateway 侧新增 `GET /healthz`（200 `{"status":"ok"}` / 503 未就绪，无鉴权，不校验下游 LLM）。落实：`docs/impl-spec/deploy/image/container-spec.md` → 重命名 `ws-container-spec.md`（git mv），新增「image 进程健康检查（healthz）」节（端点定义 + 可选 Dockerfile HEALTHCHECK + 与 entrypoint.sh 就绪探测的关系对比表）；全局引用更新：ARCHITECTURE.md、github-ci-spec.md（4 处）、ws-master.md（3 处）、deploy.md（3 处）。archived/archived-task.md 为历史快照不改。
- 2026-07-29 | 新增分阶段实现计划 `docs/impl-spec/multiple-users/phases.md`：PR0（依赖审批 docker>=7.0/pyjwt>=2.8 + 空包骨架）→ PR1（ws_master：数据层/CLI/Internal API+容器生命周期）→ PR2（ws_router：AuthProvider+JWT/auth_middleware/backend_resolve+反代/trusted_proxy+CORS）→ PR3（部署编排：Dockerfile.ws_router/ws_master + compose + 示例配置 + nginx）→ PR4（Chrome Extension Token 化）。含依赖关系图、每 PR 范围/测试/验收点、横切关注点（依赖审批/集成测试边界/Phase 1 收敛/契约稳定性）与已确认决策表 D1~D11。
- 2026-07-29 | 新增 Internal API 契约文档 `docs/impl-spec/multiple-users/internal-api-contract.md`：作为 PR1（ws_master 实现）与 PR2（ws_router 实现）的共同稳定边界。补齐 ws-master.md §6 未写全的请求/响应 schema 与错误码：统一结构化错误 `{error:{code,message,details}}`；`authenticate`/`pat/verify` 成功响应一并返回 `{user_id,user_name,display_name}`（便于 ws-router 两条认证路径下游一致）；新增 `GET /internal/users/{user_id}` 供 `/me` 查 display_name；`authenticate` 对不存在用户统一 401 防枚举；`default-ws/backend` 正在 starting 时复用 in-flight 结果最多等 `readiness_timeout` 秒再 503；PAT 明文格式 `elpat_<base62>`；`users/{id}/ws` 响应含 `container_name`。Phase 边界表标明 Phase 1 实现「不调用」的端点（`pat` POST / `users/{id}/ws` / `ws/{id}/backend` / `ws/{id}/ensure_started`）为保持 API 形状完整、避免 Phase 2 breaking。ws-master.md §6 加链接指向契约文档。
- 2026-07-29 | 多 SSO provider 支持：`users` 表删 `sso_subject` 列，新增独立 `user_identities` 表（PK `identity_id`，FK `user_id`，`provider`/`subject` UNIQUE 组合，`email`/`display_name`/`last_used_at`）。设计动机：外部 IdP 身份与本地口令凭证职责分离——`PasswordAuthProvider` 查 `users` 表，SSO provider 查 `user_identities` 表；`(provider, subject)` UNIQUE 防一身份绑两账户，`user_id` 不唯一支持一 user 绑多 provider。CLI 加 `identity list --user`、`identity unlink --id`（绑定经 OAuth flow 在线完成）。WS-Router §3.4/§3.5 更新：SSO 回调查 `user_identities` 而非 `users.sso_subject`，补多 provider 并存与绑定额外 provider 流程描述。Phase 1 schema 预留不写入，Phase 2+ 启用 SSO。

- 2026-07-29 当前 | **PR0 — 依赖与骨架**：审批通过 `docker>=7.0` 与 `pyjwt>=2.8` 两个依赖。`pyproject.toml` 新增依赖；新建 `src/everlingo/ws_router/` 与 `src/everlingo/ws_master/` 空包骨架（`__init__.py` + `__main__.py` 占位）；`main.py` 新增 `ws_router` / `ws_master` 子命令注册与 stub dispatch（`--help` 可用，不启动服务）；新增 `tests/test_multiuser_cli.py`（10 个用例：主 help 列子命令 / 子命令 help 退出码 0 / 子命令可 import）。`uv sync` 成功，全量 621 测试通过无回归。
- 2026-07-27 21:56 | Envelope 重构：`selection` + `context` 替换为 `chat_context.resource_contexts[]`（tagged union: `vault_file` / `web_page` / `selected_text`）。涉及文件：envelope.py（新增 ChatContextPart、三种 ResourceContext，删 SelectionPart/ContextPart/ScreenshotPart）；test_envelope.py（重写，新增 ChatContext / ResourceContextTaggedUnion 测试）；envelope_spec.md（重写 schema、示例）；agent.py（延续规则改为基于 resource_contexts 判空）；extension 端 extract.ts/envelope.ts/envelope.test.ts/ChatWindow.tsx（重构为 selected_text 结构）；web 端 types/chat.ts/sseClient.ts/ChatWindow.tsx（新增 resourceContextProvider 机制）；EditorApp.tsx/MilkdownEditor.tsx/SourceEditor.tsx（editorSelectionRef 获取编辑器选区实现上下文注入）；envelope-impl-spec.md 同步。
- 2026-07-27 17:00 | 拆分 `source.kind`：Chrome Extension 由 `web` 改为 `chrome_ext`，与 Standalone Web Chatbot 的 `web` 区分。涉及文件：envelope.py（新增 SourceChromeExt、收窄 SourceWeb.surface 为 fullscreen）；test_envelope.py（SourceChromeExt 测试 + surface 校验更新）；envelope_spec.md（kind 表格 + chrome_ext 节 + 示例）；extension types/envelope.ts + test（kind/类型/buildEnvelope）；文档同步（chrome-extension-spec.md / chrome-extension-impl-spec.md / envelope-impl-spec.md / web-session-acceptor.md）
- 2026-07-27 当前 | 修复 Source 模式编辑器失焦后选区高亮消失：SourceEditor.tsx 添加 CM6 `drawSelection()` 扩展，使选区高亮在点击 chatbot 侧栏后仍可见。文档同步 vault-editor.md §编辑器上下文注入。
- 2026-07-27 当前 | 修复 WYSIWYG 模式编辑器失焦后选区高亮消失：新增 `ghostSelectionPlugin.ts`（基于 ProseMirror Decoration + focus-tracking 的幽灵选区插件），接入 Milkdown 编辑器。文档同步 vault-editor.md §编辑器上下文注入。
- 2026-07-28 | 多用户部署：per-user container 路线设计文档（取代 planning-discuss.md 的进程内多 workspace 路线）。新增文档：`docs/impl-spec/multiple-users/edge.md`（Edge 服务：认证 + 反代）、`everlingo-master.md`（Master 服务：用户容器生命周期 + sqlite 数据所有者）、`external-nginx.md`（宿主现有 nginx 反代配置，含 SSE 长连接）、`deploy.md`（全容器化拓扑 + docker-compose + Dockerfile.edge/Dockerfile.master）；更新 `app-entry.md`（加 edge/master 两个进程入口）。待实现：PR1 Master 模块（docker SDK + internal API + CLI）、PR2 Edge 模块（auth 中间件 + httpx 反代含 SSE 透传 + master_client）、PR3 部署编排（compose + 外部 nginx 配置 + Dockerfile.edge/master）、PR4 Chrome Extension Token 化（替换 Basic Auth）。新增依赖（待批准写入 pyproject.toml）：`docker>=7.0`、`pyjwt>=2.8`。
- 2026-07-29 | 多用户部署设计修订：引入 `workspace container`（ws-container）一等概念，把容器生命周期与 user 身份解耦，支持未来单 user 多 ws。重命名：`edge`→`ws_router`、`master`→`ws_master`（CLI 子命令 + 源码包 `src/everlingo/ws_router/`、`ws_master/` + 配置 `ws_router.yaml`/`ws_master.yaml` + DB `ws_master.sqlite` + 镜像 `everlingo-ws-router`/`everlingo-ws-master` + Dockerfile `Dockerfile.ws_router`/`Dockerfile.ws_master`）；文档文件 `everlingo-master.md`→`ws-master.md`、`edge.md`→`ws-router.md`（git mv）。数据模型：`containers` 表→`ws_containers` 表（PK 改 `ws_container_id`，新增 `is_default`/`docker_container_id`/`host_workspace_dir`/`error_message`，删 `users.workspace_dir`）；`users` 表新增 nullable `openai_*` 四字段（远期 per-user key 预留）。状态机：`absent/creating/starting/started/stopped/error` + 并发控制（per-ws asyncio.Lock）+ WS-Master 启动对账。配置拆分：LLM 配置留 `ws_master.yaml`（容器 env 注入，不落盘），新增 `ws_container_everlingo_template.yaml`（openai_* 留空 env fallback，language 默认值可覆盖）。API 多 ws 形状：`GET /internal/users/{uid}/ws`、`GET /internal/ws/{id}/backend`、便捷端点 `GET /internal/users/{uid}/default-ws/backend`（Phase 1 ws-router 实用）；删 `GET /internal/users/{uid}/backend`。容器名 `everlingo-<user_name>-<short_id>`；目录 `<host_ws_dir>/<user_name>/<ws_container_id>/`。待实现 PR 更新：PR1 ws_master 模块、PR2 ws_router 模块、PR3 部署编排（Dockerfile.ws_router/ws_master + 模板挂载）、PR4 Chrome Extension Token 化。
- 2026-07-29 | Dockerfile 加 HEALTHCHECK + ws-container-spec.md 同步：`docs/impl-spec/deploy/image/Dockerfile` 新增 `HEALTHCHECK` 指令（`--interval=30s --timeout=5s --start-period=60s --retries=3`，CMD 用 python urllib 探 `http://127.0.0.1:8000/healthz`）。`start-period=60s` 覆盖 indexer 冷启（unidic-lite 词典加载 + sqlite 初始化）避免误判 unhealthy。`ws-container-spec.md` healthz 节从「计划新增」语气改为「已实现」：动机段改过去时；端点响应补 503 体 `{"status":"error","reason":"gateway_not_initialized"|"indexer_not_ready"}`；新增「就绪判定」条件（`_gateway` 注入 + `indexer.mcp.url` 存在）与「不校验项」（不做 TCP 端口探测/不校验 LLM 可达性）两小节；Dockerfile HEALTHCHECK 节从「可选」改为「已配置」、示例 start-period 30s→60s、补 interval/retries 说明与单用户自愈场景。
- 2026-07-29 | 实现 `/healthz` 端点：`src/everlingo/gateway/web_acceptor.py` 新增 `GET /healthz`（注册在 catch-all `/{path:path}` 之前）。就绪判定（本地同步、无网络 IO）：`_gateway is None` → 503 `gateway_not_initialized`；`indexer.mcp.url` 文件不存在 → 503 `indexer_not_ready`；否则 200 `{"status":"ok"}`。不做 TCP 端口探测（entrypoint.sh 已保证启动时 indexer 端口通，运行中崩溃由 WS-Master healthcheck task 兜底）与 LLM 可达性校验（请求时按需失败重试）。新增依赖导入 `JSONResponse` 与 `indexer_mcp_url_path`。测试 `tests/test_web_acceptor.py::TestHealthz` 4 个用例：就绪 200 / gateway 未初始化 503 / indexer 未就绪 503 / 路由顺序在 catch-all 之前。全量 23 测试通过无回归。
- 2026-07-29 | ws-container 健康检查端点设计 + 文件重命名：发现现有 workspace container 对外无 health check（entrypoint.sh 仅做容器内 indexer→gateway 顺序探测，web_acceptor.py 无 /healthz 端点），WS-Master lazy start 状态机 §6.1/§7 依赖「探活通过」无从实现。决策方案 A：gateway 侧新增 `GET /healthz`（200 `{"status":"ok"}` / 503 未就绪，无鉴权，不校验下游 LLM）。落实：`docs/impl-spec/deploy/image/container-spec.md` → 重命名 `ws-container-spec.md`（git mv），新增「image 进程健康检查（healthz）」节（端点定义 + 可选 Dockerfile HEALTHCHECK + 与 entrypoint.sh 就绪探测的关系对比表）；全局引用更新：ARCHITECTURE.md、github-ci-spec.md（4 处）、ws-master.md（3 处）、deploy.md（3 处）。archived/archived-task.md 为历史快照不改。
- 2026-07-29 | 新增分阶段实现计划 `docs/impl-spec/multiple-users/phases.md`：PR0（依赖审批 docker>=7.0/pyjwt>=2.8 + 空包骨架）→ PR1（ws_master：数据层/CLI/Internal API+容器生命周期）→ PR2（ws_router：AuthProvider+JWT/auth_middleware/backend_resolve+反代/trusted_proxy+CORS）→ PR3（部署编排：Dockerfile.ws_router/ws_master + compose + 示例配置 + nginx）→ PR4（Chrome Extension Token 化）。含依赖关系图、每 PR 范围/测试/验收点、横切关注点（依赖审批/集成测试边界/Phase 1 收敛/契约稳定性）与已确认决策表 D1~D11。
- 2026-07-29 | 新增 Internal API 契约文档 `docs/impl-spec/multiple-users/internal-api-contract.md`：作为 PR1（ws_master 实现）与 PR2（ws_router 实现）的共同稳定边界。补齐 ws-master.md §6 未写全的请求/响应 schema 与错误码：统一结构化错误 `{error:{code,message,details}}`；`authenticate`/`pat/verify` 成功响应一并返回 `{user_id,user_name,display_name}`（便于 ws-router 两条认证路径下游一致）；新增 `GET /internal/users/{user_id}` 供 `/me` 查 display_name；`authenticate` 对不存在用户统一 401 防枚举；`default-ws/backend` 正在 starting 时复用 in-flight 结果最多等 `readiness_timeout` 秒再 503；PAT 明文格式 `elpat_<base62>`；`users/{id}/ws` 响应含 `container_name`。Phase 边界表标明 Phase 1 实现「不调用」的端点（`pat` POST / `users/{id}/ws` / `ws/{id}/backend` / `ws/{id}/ensure_started`）为保持 API 形状完整、避免 Phase 2 breaking。ws-master.md §6 加链接指向契约文档。
- 2026-07-29 | 多 SSO provider 支持：`users` 表删 `sso_subject` 列，新增独立 `user_identities` 表（PK `identity_id`，FK `user_id`，`provider`/`subject` UNIQUE 组合，`email`/`display_name`/`last_used_at`）。设计动机：外部 IdP 身份与本地口令凭证职责分离——`PasswordAuthProvider` 查 `users` 表，SSO provider 查 `user_identities` 表；`(provider, subject)` UNIQUE 防一身份绑两账户，`user_id` 不唯一支持一 user 绑多 provider。CLI 加 `identity list --user`、`identity unlink --id`（绑定经 OAuth flow 在线完成）。WS-Router §3.4/§3.5 更新：SSO 回调查 `user_identities` 而非 `users.sso_subject`，补多 provider 并存与绑定额外 provider 流程描述。Phase 1 schema 预留不写入，Phase 2+ 启用 SSO。

- 2026-07-26 02:35 | **消除 chown 层导致的镜像层膨胀（docker pull 每次重下 200M+）**
  - 根因：`Dockerfile` runtime stage 中 `RUN chown -R everlingo:everlingo /app` 位于 `COPY src/ src/` 之后；src 变更使该层重算，将整个 /app（含 ~300M .venv）的所有权元数据写进新层，每次 pull 必须重传此大层
  - 修复：runtime stage 所有 COPY 添加 `--chown=everlingo:everlingo`，**删除** `RUN chown -R` 行
  - 更新 `container-spec.md` Stage 3 描述，附注 rationale
- 2026-07-25 22:48 | **GitHub Actions 多架构镜像发布 CI**
  - 新建 `.github/workflows/docker-release.yml`：`v*` tag / `workflow_dispatch` 触发；双 native runner（amd64=`ubuntu-24.04`，arm64=`ubuntu-24.04-arm`）并行 build，再 `manifest` job 用 `docker buildx imagetools create` 合并为多架构 manifest
  - Tag 规则：`v1.2.3`→`1.2.3`/`1.2`/`1`/`latest`；`v1.2.3-rc.1`→`1.2.3-rc.1`/`1.2.3`（无 latest）；dispatch→`dev-<run_id>` 或 `dev-<run_id>-<suffix>`
  - metadata-action 生成 base tag，自定义 step 用 sed 给每条 tag 追加 `-amd64`/`-arm64` 后缀作为单架构镜像 tag；manifest job 遍历 base tag 列表合并
  - GHA cache `type=gha,mode=max`，scope 分 arch（`everlingo-amd64`/`everlingo-arm64`）
  - GHCR 认证用默认 `GITHUB_TOKEN`；permissions `contents: read`/`packages: write`
  - 新建 `docs/impl-spec/CI/github-ci-spec.md`：触发条件、构建策略、tag 规则、GHCR 可见性配置、仓库权限要求、发布流程、链接到 container-spec.md

- 2026-07-25 XX:XX | **Image 设计规范文档修订（container-spec.md）**
  - 重写 `docs/impl-spec/deploy/image/container-spec.md`：新增「镜像构建」（多阶段 frontend-builder/deps/runtime）「镜像内目录布局」「workspace 挂载策略」节；重写「image 进程」节为 entrypoint.sh 编排（bash + wait -n + /dev/tcp 就绪探测）；「image expose port」仅 8000（删 9000）；修复「经典部署方法」`docker run -v` 参数位置 bug、`$your_domain` → `<your_domain>` 占位符、删注释段、`app_user_name` 加注释；新增 `openai_embedding_model` 字段说明
  - 修订 `root/.../everlingo.yaml` 模板：补 `openai_embedding_model: ''` 字段 + `interface: 0.0.0.0` 注释（容器部署有意为之）
  - `ARCHITECTURE.md` 新增「部署」节链接指向 container-spec.md
  - 决策汇总：进程编排 entrypoint.sh + wait -n；前端 Node 多阶段构建；运行时 python -m everlingo；build 期 uv sync + unidic download；镜内 /app/src + /app/web/dist WORKDIR /app；整目录挂载覆盖；日志写文件；保留 sudo；不加 HEALTHCHECK；indexer 就绪轮询 indexer.mcp.url + /dev/tcp；EVERLINGO_WORKSPACE_DIR env 设为 default workspace 路径
  - 创建 `docs/impl-spec/deploy/image/Dockerfile`：三阶段构建（frontend-builder/deps/runtime），runtime 阶段 `COPY docs/impl-spec/deploy/image/root/ /`（context=repo root）
  - 创建 `docs/impl-spec/deploy/image/root/app/entrypoint.sh`：bash + wait -n + /dev/tcp 就绪探测，统一 python -m everlingo 命令

- 2026-07-25 XX:XX | **Web Chatbot SSE 自动重连 + session_expired 处理**
  - `sseClient.ts`：`connectSSE` 重写，`onerror` 按 `readyState` 区分网络异常（`CONNECTING` → `scheduleRetry()`）与 session 过期（`CLOSED` → `session_expired`）；指数退避 1→2→4→8→16→30s 封顶；`onStatus` 回调通知 `connected`/`reconnecting` + 倒计时秒数 / `session_expired`；暴露 `retryNow()`
  - `ChatWindow.tsx`：`error` 拆分为 `connStatus`（连接）+ `error`（业务）；amber 色提示条在 `reconnecting` 时显示倒计时及「立即重试」按钮，`session_expired` 时显示「会话已过期 [重新开始]」；`handleRebuild` 创建新 session + 插入系统消息；`reconnectNonce` 触发 useEffect 重跑；正常/重连成功不显示；非连接错误保持红色 banner
  - `MessageBubble.tsx` + `types/chat.ts`：增加 `from: 'system'` 类型，渲染为居中灰色文本
  - `docs/impl-spec/web-chatbot.md` 新增「SSE 自动重连」小节，含 `session_expired` 分支
- 2026-07-25 XX:XX | **Web Chatbot 移动端响应式适配**
  - 断点 `md` (768px)：所有响应式差异用 `md:` 前缀表达，纯 CSS 方案
  - 按钮文字用 `<span className="hidden md:inline">` 包裹，移动端仅显示图标（笔记编辑器、发送）
  - 「发送」按钮移动端缩小为方形 icon button（`w-9` + `aria-label`）
  - 容器 padding/border 响应式：`ChatWindow` 根 `px-0 md:px-6`、header/messages/input padding 收紧
  - `TaskSelector` 纯文字按钮保持不动
  - 更新 `docs/impl-spec/web-chatbot.md` 新增「移动端适配」一节
- 2026-07-24 XX:XX | **Vault Editor 移动端适配**
  - 断点 `md` (768px)：`< md` 移动端抽屉模式，`>= md` 桌面三栏 flex 不变
  - 按钮文字用 `<span className="hidden md:inline">` 包裹，移动端仅显示图标
  - Header 改 flex 布局，新增汉堡按钮（`Menu` 图标，`md:hidden`），toggle 左栏
  - 左栏/右栏 aside `< md` 时改为 `fixed` overlay + `translate-x` 滑入/滑出
  - 新增 backdrop（`z-30 bg-black/40`），点击关闭所有抽屉
  - 移动端抽屉互斥：打开一个自动关闭另一个
  - Resize 手柄加 `hidden md:block`，移动端隐藏
  - 新增 `useMediaQuery` hook（`matchMedia` + listener）
  - 更新 `docs/impl-spec/vault-editor.md` 移动端小节
- 2026-07-25 XX:XX | **unidic → unidic-lite（缩小镜像体积）**
  - `pyproject.toml`：`"unidic>=1.1.0"` → `"unidic-lite>=1.0.8"`
  - `uv lock` 重新生成，移除 unidic 1.1.0，新增 unidic-lite 1.0.8
  - `Dockerfile`：删 `python -m unidic download` 行，deps stage 不再需要下载步骤（unidic-lite 词典打包在 wheel 中）
  - `tokenizer.py`：注释更新 unidic → unidic-lite；代码逻辑不变（unidic-lite 是 unidic 的 drop-in 替代，同样提供 `unidic.DICDIR` / `unidic.__version__`）
  - 文档：`container-spec.md` / `memory-vault-search-spec.md` / `github-ci-spec.md` / `search-api-spec.md` / `search.drawio.svg` 中的 unidic 引用统一改为 unidic-lite
    - 收益：镜像体积减少 ~450MB，构建少一次联网下载
  - 验证：`uv sync --frozen` + `uv run python -c "import unidic; from everlingo.mem.vault.search.tokenizer import _load_fugashi, tokenizer_version; assert _load_fugashi() is not None; print(tokenizer_version())"` 输出含 `unidic-lite:unidic-3.1.0+2021-08-31`
- 2026-07-25 XX:XX | **Dockerfile 缓存优化**
  - Stage 1 `frontend-builder`：先 COPY `package.json`+`package-lock.json` → `npm ci`，再 COPY `web/` → `npm run build`，使 `npm ci` 层只随 lockfile 失效
  - Stage 2 `deps`：移除 `COPY src/`，改为 `uv sync --no-install-project`（.venv 不含本地包），再 `unidic download`；两层均只依赖 `pyproject.toml`/`uv.lock`，src 改动不再触发 unidic 重下载
  - Stage 3 `runtime`：新增 `ENV PYTHONPATH="/app/src"` 补偿缺少的 editable .pth
  - 参考：`docs/impl-spec/deploy/image/Dockerfile`
- 2026-07-25 XX:XX | **为 Web Chatbot 与 Vault Editor 添加 favicon**
  - 源图 `docs/arts/chrome-icon.png` → `web/public/favicon.png`（Vite `public/` 部署）
  - `web/index.html` 与 `web/editor.html` 均添加 `<link rel="icon">`
  - 更新 `docs/impl-spec/web-chatbot.md` 与 `docs/impl-spec/vault-editor.md` 文档
- 2026-07-24 XX:XX | **最小化 frontmatter 必选字段 + slug 移出 frontmatter**
  - 方案 B：file_path 作 upsert 主键，ulid 列可空（SQLite UNIQUE 已允许多 NULL，无需 schema 迁移）
  - 代码：indexer._get_existing_rowid / sync.reconcile / watcher._dispatch 改按 file_path 查询
  - 新增 get_by_file_path()；ParsedDoc.ulid 改为 str | None
  - SearchHit.ulid 改为 str | None（protocol.py）
  - slug 移出 frontmatter：从文件名 `Path(rel).stem` 派生（frontmatter 有 slug 仍优先）
  - 移除 `"slug"` 从 _PROTECTED_FRONTMATTER_FIELDS 及相关 prompt
  - 更新 vault_spec.md / kb_items_spec_*.md / search-spec / agent.py / memory_writer_action.py 文档
  - 测试：missing-ulid 改成功 case；新增无 ulid index_file 测试、slug 从文件名派生测试
  - 影响范围：151 vault 搜索测试 + 50 writer agent 测试全部通过
- 2026-07-26 02:50 | **修复 `import unidic` 包名 bug（容器镜像中日文退化为字符切分）**
  - **背景**：上次迁移 `unidic → unidic-lite` 后，`tokenizer.py` 仍用 `import unidic`，但 `unidic-lite` 提供的 import 名是 **`unidic_lite`**（下划线），而非 `unidic`。本机 venv 因残留了旧版完整 `unidic` 的 `dicdir/` 目录（182MB，无 `__init__.py`，被 Python 当 namespace package）导致 `import unidic` 走通，掩盖了 bug。容器为干净环境，仅装 `unidic-lite`，`import unidic` 直接抛 `ModuleNotFoundError`，日文退化为字符切分。
  - **更正**：上次移植条目 L49 的断言「unidic-lite 是 unidic 的 drop-in 替代，同样提供 `unidic.DICDIR` / `unidic.__version__`」——**不成立**。unidic-lite 只提供 `unidic_lite.DICDIR` / `unidic_lite.VERSION`，不提供 `unidic` 模块。
  - `tokenizer.py`：两处 `import unidic` → `import unidic_lite`；`getattr(unidic, 'DICDIR', None)` → `getattr(unidic_lite, 'DICDIR', None)`；`getattr(unidic, '__version__', None)` → `getattr(unidic_lite, 'VERSION', None)`；日志文案 `unidic 不可用` → `unidic-lite 不可用`
  - 本机 venv：删除残留的 `.venv/lib/python3.12/site-packages/unidic/`（182MB 旧 dicdir + unidic.zip），`uv sync --frozen` 后验证 `import unidic_lite` 且 `_load_fugashi()` 返回正常 tagger
  - 测试：`uv run --with pytest pytest tests/test_mem_vault_search_tokenizer.py -v` 10 passed
- 2026-07-26 22:28 | **Chrome Extension 支持 HTTP Basic Auth（Nginx Basic Auth）**
  - 新增依赖 `@microsoft/fetch-event-source`（替换原生 `EventSource`，因无法自定义请求头）
  - `config.ts`：新增 `SERVER_USERNAME_STORAGE_KEY` / `SERVER_PASSWORD_STORAGE_KEY`、`getApiAuth()`、`buildBasicAuthHeader()`（空 username → `null`，不启用 auth）、`getApiConfig()`
  - `OptionsForm.tsx`：新增「服务端用户名」「服务端密码」输入框（密码框含眼睛切换图标）+「测试连接」按钮（`GET /api/session/__probe__/events` + 3s 超时）
  - `sseClient.ts`：`sendEnvelope` / `connectSSE` 新增可选 `authHeader` 参数；`connectSSE` 用 `fetchEventSource` 替代 `EventSource`
  - `background.ts`：`probeSession` / `createSession` 通过 `getApiConfig()` 注入 Authorization header
  - `ChatWindow.tsx`：init 时 `getApiConfig()` 获取 authHeader，传给外层所有 `sendEnvelope` / `connectSSE` 调用
  - 单元测试：`config.test.ts` 新增 `buildBasicAuthHeader`（空/Unicode/冒号密码等）；`sseClient.test.ts` 新增 11 条（mock fetchEventSource，验证 header 注入、event 分发、abort 清理）
  - 文档：`chrome-extension-impl-spec.md` §7 config.ts + §9 sseClient.ts + §14.1 Options；`chrome-extension-spec.md` §4 权限表
- 2026-07-26 02:50 | **修复 vec0 KNN 在容器中因 SQLite 版本差异（3.40.1 vs 3.45.1）报错 `LIMIT ?` 不可用**
  - **根因**：`python:3.12.13-bookworm` 链接系统 SQLite **3.40.1**，不把 `LIMIT ?`（绑定参数）作为约束传给 vec0 xBestIndex；本地 dev（SQLite 3.45.1）通过但容器抛错
  - `src/everlingo/mem/vault/search/embedding/store.py:230` `_vec0_knn`：`LIMIT ?` → `AND k = ?`（sqlite-vec 官方写法，两端兼容）
  - `docs/impl-spec/search/memory-vault-embedding-spec.md`：「过滤策略」处注明 `k = ?` 语法选择与 SQLite 版本约束
  - 验证：容器内 `k = ?` 实测通过；本地现有 `test_knn*` 全部通过
  - **背景**：上次迁移 `unidic → unidic-lite` 后，`tokenizer.py` 仍用 `import unidic`，但 `unidic-lite` 提供的 import 名是 **`unidic_lite`**（下划线），而非 `unidic`。本机 venv 因残留了旧版完整 `unidic` 的 `dicdir/` 目录（182MB，无 `__init__.py`，被 Python 当 namespace package）导致 `import unidic` 走通，掩盖了 bug。容器为干净环境，仅装 `unidic-lite`，`import unidic` 直接抛 `ModuleNotFoundError`，日文退化为字符切分。
  - **更正**：上次移植条目 L49 的断言「unidic-lite 是 unidic 的 drop-in 替代，同样提供 `unidic.DICDIR` / `unidic.__version__`」——**不成立**。unidic-lite 只提供 `unidic_lite.DICDIR` / `unidic_lite.VERSION`，不提供 `unidic` 模块。
  - `tokenizer.py`：两处 `import unidic` → `import unidic_lite`；`getattr(unidic, 'DICDIR', None)` → `getattr(unidic_lite, 'DICDIR', None)`；`getattr(unidic, '__version__', None)` → `getattr(unidic_lite, 'VERSION', None)`；日志文案 `unidic 不可用` → `unidic-lite 不可用`
  - 本机 venv：删除残留的 `.venv/lib/python3.12/site-packages/unidic/`（182MB 旧 dicdir + unidic.zip），`uv sync --frozen` 后验证 `import unidic_lite` 且 `_load_fugashi()` 返回正常 tagger
  - 测试：`uv run --with pytest pytest tests/test_mem_vault_search_tokenizer.py -v` 10 passed

  - 2026-07-22 12:00 | vault-editor PR 5：FileTree 新建/重命名/删除文件和目录 + 右键/长按 ContextMenu + 行内输入
  - 2026-07-22 17:00 | mem_writer_agent: vault_spec.md 改由 compile_prompt 加载入 system prompt，不再由 LLM 运行时 read(path=...)
  - 2026-07-22 19:00 | 知识点类型唯一事实来源：vault_spec.md，移除代码中 ItemType Literal[5] 硬编码，mem_entry_spec.md 改为引用 vault_spec.md，更新设计文档
  - 2026-07-22 20:00 | editor URL 同步：选中文件后通过 history.replaceState 将 lang+path 反映到地址栏，覆盖 spec 与 TASKS.md
  - 2026-07-22 22:00 | 搜索支持 tag-only（q 可空）+ 搜索模式标签改中文（混合/精确/语义）
  - 2026-07-22 23:00 | editor FileTree header 工具栏 + 刷新按钮（整树重拉）；DRY 重构 4 处重复 tree 重拉
  - 2026-07-23 10:00 | 修复刷新后已懒加载目录无法再展开：将 loaded 标记从组件 useRef 移到 Entry.loaded 数据字段，刷新/切语言时随整树重拉重置，重新点开按需懒加载
  - 2026-07-23 11:00 | editor header 改造：标题居中「🐹 小记笔记编辑器」去掉 svg 图标；模式切换文案 Source/WYSIWYG → 源码/直观；同步 editor.html 标题与 vault-editor.md 文档术语
  - 2026-07-23 12:00 | editor header 增加「呼叫小记」（右侧打开可调宽 chatbot 侧栏，session 常驻）与「转到小记」（跳转 /）按钮
  - 2026-07-23 14:00 | standalone chatbot header 增加「笔记编辑器」按钮，点击跳转 /editor；仅非嵌入式模式显示；更新设计文档
  - 2026-07-23 15:00 | 将 editor header 上的「源码/直观」模式切换和「保存」按钮移至编辑区上方文件路径面板右侧；header 仅保留 lang selector、标题、呼叫小记、转到小记
  - 2026-07-23 16:00 | SearchBar tag 候选列表增加刷新按钮（RefreshCw），手动重拉 list_tags 以同步笔记 tag 增删；tags 区块常驻显示（无 tag 时显示「暂无 tag」提示）；修复 tag 切换 lang 时 filter 闭包 bug；更新 vault-editor.md 设计文档
  - 2026-07-24 10:00 | PR1: 加入配置项 plugins.channels.channel_web（listener + public_address.base_url）；新增 WebListener/WebPublicAddress/ChannelWeb/Channels/Plugins 模型；setting.py 新增 get_web_listener/get_web_public_base_url helper；gateway.py WebSessionAcceptor 接入 listener 配置；更新 configuration.md / web-session-acceptor.md / vault-editor.md 文档；新增 55 项 plugins 配置测试，全量 566 通过
  - 2026-07-24 11:00 | PR2: Chat Agent 输出笔记文件地址时用 markdown link 指向 Vault Editor。agent.py _build_system_prompt 新增 public_address_base_url 参数；## 基本配置 加 target_lang_code 与 public_address_base_url 两行；## 笔记 Vault / 知识库 节新增 ### 笔记文件地址的输出格式 子节（示例 URL 用 base_url + lang=代码 + url-encoded path）；_refresh_agent_if_needed 通过 setting.get_web_public_base_url() 获取并传入；更新 chat-agent-spec.md；新增 TestNoteFileLinkFormat 5 项测试，agent 相关 116 项测试通过
  - 2026-07-24 12:00 | PR3: Web Chatbot 链接点击行为。MarkdownRenderer 自定义 `<a>` 组件加 `target="_blank"` + `LinkListenerContext`；ChatWindow 新增 `linkListener` prop 经 Context 下发；EditorApp 新增 `openFileContent`/`loadFile`/`handleChatLinkClick`，嵌入时拦截 `/editor` 同源链接同窗打开文件（切 lang + 重拉 tree + read），独立 chatbot / 外链 / 非 `/editor` 路径回退新 Tab；更新 vault-editor.md / web-chatbot.md 文档
  - 2026-07-24 13:00 | Chrome Extension sidecar 链接新 Tab 打开：MarkdownRenderer 自定义 `<a>` 组件加 `target="_blank" rel="noopener noreferrer"`；不引入 LinkListenerContext（sidecar 无宿主嵌入场景）；更新 chrome-extension-impl-spec.md 文档
  - 2026-07-24 17:00 | FileTree 显示名优化：后端 tree 端点遍历 entries 读 frontmatter 前 4KB 注入 `title`（文件取自身 title，目录取 index.md 的 title，index.md 文件自身不注入 title）；前端 Entry 类型增 `title` 字段，FileTree 显示用 `title ?? name`（index.md 永远显示 index.md）；更新 vault-editor.md 文档与 TASKS.md
  - 2026-07-24 19:00 | FileTree 与搜索索引过滤 OS 隐藏文件/目录（dotfile/dotdir，name 以 `.` 开头）：API tree 端点新增 _filter_hidden_entries 硬过滤；is_excluded_vault_file 增加 dotfile 排除（walk_vault/sync/watcher 三处受益）；更新 vault-editor.md / vault-mcp-spec.md / memory-vault-search-spec.md 文档与测试
  - 2026-07-24 18:00 | WYSIWYG 模式点击 markdown 内链接支持：单击 `<a>` 触发链接跳转。外链新 tab 打开；同源 `/editor?lang=...&path=...` 及 vault 相对/绝对路径在当前编辑区加载（未保存 confirm、跨 lang 自动切换）；Source 模式不做处理。更新 vault-editor.md 文档与 TASKS.md

  - 2026-07-22 12:00 | vault-editor PR 5：FileTree 新建/重命名/删除文件和目录 + 右键/长按 ContextMenu + 行内输入
  - 2026-07-22 17:00 | mem_writer_agent: vault_spec.md 改由 compile_prompt 加载入 system prompt，不再由 LLM 运行时 read(path=...)
  - 2026-07-22 19:00 | 知识点类型唯一事实来源：vault_spec.md，移除代码中 ItemType Literal[5] 硬编码，mem_entry_spec.md 改为引用 vault_spec.md，更新设计文档
  - 2026-07-22 20:00 | editor URL 同步：选中文件后通过 history.replaceState 将 lang+path 反映到地址栏，覆盖 spec 与 TASKS.md
  - 2026-07-22 22:00 | 搜索支持 tag-only（q 可空）+ 搜索模式标签改中文（混合/精确/语义）
  - 2026-07-22 23:00 | editor FileTree header 工具栏 + 刷新按钮（整树重拉）；DRY 重构 4 处重复 tree 重拉
  - 2026-07-23 10:00 | 修复刷新后已懒加载目录无法再展开：将 loaded 标记从组件 useRef 移到 Entry.loaded 数据字段，刷新/切语言时随整树重拉重置，重新点开按需懒加载
  - 2026-07-23 11:00 | editor header 改造：标题居中「🐹 小记笔记编辑器」去掉 svg 图标；模式切换文案 Source/WYSIWYG → 源码/直观；同步 editor.html 标题与 vault-editor.md 文档术语
  - 2026-07-23 12:00 | editor header 增加「呼叫小记」（右侧打开可调宽 chatbot 侧栏，session 常驻）与「转到小记」（跳转 /）按钮
  - 2026-07-23 14:00 | standalone chatbot header 增加「笔记编辑器」按钮，点击跳转 /editor；仅非嵌入式模式显示；更新设计文档
  - 2026-07-23 15:00 | 将 editor header 上的「源码/直观」模式切换和「保存」按钮移至编辑区上方文件路径面板右侧；header 仅保留 lang selector、标题、呼叫小记、转到小记
  - 2026-07-23 16:00 | SearchBar tag 候选列表增加刷新按钮（RefreshCw），手动重拉 list_tags 以同步笔记 tag 增删；tags 区块常驻显示（无 tag 时显示「暂无 tag」提示）；修复 tag 切换 lang 时 filter 闭包 bug；更新 vault-editor.md 设计文档
  - 2026-07-24 10:00 | PR1: 加入配置项 plugins.channels.channel_web（listener + public_address.base_url）；新增 WebListener/WebPublicAddress/ChannelWeb/Channels/Plugins 模型；setting.py 新增 get_web_listener/get_web_public_base_url helper；gateway.py WebSessionAcceptor 接入 listener 配置；更新 configuration.md / web-session-acceptor.md / vault-editor.md 文档；新增 55 项 plugins 配置测试，全量 566 通过
  - 2026-07-24 11:00 | PR2: Chat Agent 输出笔记文件地址时用 markdown link 指向 Vault Editor。agent.py _build_system_prompt 新增 public_address_base_url 参数；## 基本配置 加 target_lang_code 与 public_address_base_url 两行；## 笔记 Vault / 知识库 节新增 ### 笔记文件地址的输出格式 子节（示例 URL 用 base_url + lang=代码 + url-encoded path）；_refresh_agent_if_needed 通过 setting.get_web_public_base_url() 获取并传入；更新 chat-agent-spec.md；新增 TestNoteFileLinkFormat 5 项测试，agent 相关 116 项测试通过
  - 2026-07-24 12:00 | PR3: Web Chatbot 链接点击行为。MarkdownRenderer 自定义 `<a>` 组件加 `target="_blank"` + `LinkListenerContext`；ChatWindow 新增 `linkListener` prop 经 Context 下发；EditorApp 新增 `openFileContent`/`loadFile`/`handleChatLinkClick`，嵌入时拦截 `/editor` 同源链接同窗打开文件（切 lang + 重拉 tree + read），独立 chatbot / 外链 / 非 `/editor` 路径回退新 Tab；更新 vault-editor.md / web-chatbot.md 文档

2026-07-20 20:00 | Chat Agent 提交 mem_entry 添加 DEBUG 日志（create + delete/edit 两路径）- 全量 model_dump
2026-07-20 21:00 | Memory Writer Agent system prompt 注入 envelope_spec.md，解释 new_messages / context_messages 中的 Envelope 格式；重构为共用一条 MCP session 加载两个 spec
2026-07-21 10:00 | Standalone Web Chatbot 加入 task 单选按钮（翻译/查词/聊天），迁移到 envelope 结构化协议；更新相关设计文档
2026-07-21 11:00 | Chat Agent envelope 改为运行期 MCP compile_prompt 加载（与 Memory Writer 一致）；意图识别节新增 envelope.task 作用说明；_call_compile_prompt 迁移到共享的 mem_writer_mcp_client
2026-07-21 12:00 | 修复 7 个测试文件中的 20+ 个失败用例：agent.ainvoke 改用 AsyncMock（test_mem_writer_agent / test_agent_system_notice / test_gateway）；_disable_embedding autouse fixture（conftest.py）；LLM ainvoke try/except（agent.py）；assertions 更新（test_unified_agent.py）；channel.send_sound AsyncMock（test_voice_tool.py）；_cleanup_everlingo_handlers 防止日志处理器泄露（test_log_utils.py）
2026-07-21 16:00 | Vault Editor PR 1：后端 REST→MCP 翻译层。新增 vault_editor_mcp_client.py（per-request 临时 MCP stream）、vault_editor_api.py（/api/vault/* 共 11 个端点 + 错误映射 + rename 复合 + tmp 过滤）、test_vault_editor_api.py（25 个 mock 单测覆盖全线），挂载到 web_acceptor.py
2026-07-21 19:30 | Vault Editor PR 2：Vite 多入口改造 + editor 骨架。web/vite.config.ts 多入口（main+editor）；新增 editor.html、web/src/editor/（main.tsx、EditorApp.tsx 三栏布局+状态总管、FileTree.tsx 递归文件树、MilkdownEditor.tsx textarea 占位、vaultApi.ts fetch 封装、types/vault.ts）；web_acceptor.py /editor 路由 catch-all；test_web_acceptor.py 补 4 个 /editor 路由用例（全量 19 pass）；npm run build 双入口构建通过
2026-07-21 22:00 | FileTree 懒加载：vaultApi.ts tree() 增 path/depth 参数；FileTree.tsx 展开空 children 目录时按需调用 onLazyLoad 拉取子目录；EditorApp.tsx 增 mergeChildren + handleLazyLoad；test_vault_editor_api.py 补 tree(with path) 用例；vault-editor.md 补子目录懒加载说明
2026-07-21 23:00 | Vault Editor PR 3：接入 Milkdown + 双模式切换。新增 @milkdown/kit @milkdown/react 依赖；MilkdownEditor.tsx 重写为 source textarea / WYSIWYG Milkdown 双模式（key-based remount 切文件/模式，listener 插件回传 markdown onChange，skipFirst ref 防初始回调）；EditorApp.tsx 增 mode state + localStorage 持久化、Header 二态 toggle 按钮（Source / WYSIWYG）、mode 透传 + key 驱动 remount；index.css 无新增（editor/main.tsx import prosemirror.css，Milkdown 内联 style 标签）
2026-07-22 11:00 | Vault Editor Source 模式接入 CodeMirror 6 语法高亮：新增 SourceEditor.tsx（CM6 markdown 语言 + language-data 围栏代码按 yaml/json/bash 自动着色 + 自定义 oklch HighlightStyle + lineWrapping 无行号）；MilkdownEditor.tsx source 分支替换 textarea → SourceEditor；package.json 显式声明 codemirror/@codemirror/* 7 个 + @lezer/highlight 共 8 个依赖；vault-editor.md 补 Source 模式说明
2026-07-22 12:00 | Vault Editor PR 4：搜索栏 + tag 过滤 + 左栏可调宽。types/vault.ts 新增 SearchReq/SearchHit/SearchResp/TagCount/TagsResp 等类型；vaultApi.ts 新增 search()/listTags()；SearchBar.tsx 新建（搜索框、mode toggle、tag 多选 Badge 切换、tags_op and/or、结果列表，点击结果不切 tab 仅 handleFileSelect）；EditorApp.tsx 左栏改 Files/Search Tab 切换（hidden 保留状态）+ 可拖拽调整宽度（Pointer Events，百分比 localStorage，默认 22% 范围 15-50%）+ URL q/tag 参数解析与预填；vault-editor.md 设计同步

- 2026-07-20 | **侧边栏 fontSize 调大**: `extension/src/index.css` 设置 `html { font-size: 17px }`，等比放大所有 `text-*` rem 类，提升 sidecar 可读性；同步更新 `chrome-extension-impl-spec.md` §10 注释
- 2026-07-20 | **设计 + 实现**: Chrome Extension 选词翻译 sidecar
  - **设计文档**：[chrome-extension-spec.md](/docs/impl-spec/chrome-extension-spec.md)（架构/session 生命周期/envelope 构造/UI history）+
    [chrome-extension-impl-spec.md](/extension/chrome-extension-impl-spec.md)（实现详细设计）
  - **Schema 扩展**：`SourceWeb.surface` 字段（sidecar/popup/fullscreen，默认 fullscreen）+ `ContextPart.screenshot` 可选 + `ScreenshotPart` model
  - **Agent system prompt**：`task=look_up` 空输入延续语义规则；source 字段说明更新（已落地 plain 与 web）
  - **WebChannel 超时**：`DISCONNECT_GRACE` 300s → 1200s
  - **Chrome Extension 代码**（`extension/` 子目录）：
    - Scaffold：package.json / tsconfig / vite multi-entry / manifest.json MV3 / index.css / placeholder icons
    - Background service worker：device_id 生成、GET_SESSION 消息处理、session 探活/创建/重用
    - 类型 + 纯函数：envelope TS 类型（含 buildEnvelope）、extract.ts（selection + context.text 算法 + captureSnapshot）
    - Services：sseClient（全 URL + envelope body）/ backgroundClient / messageHistory（chrome.storage.session UI history 持久化）
    - Sidecar panel React 组件：ChatWindow（session 查询 + UI history 恢复 + envelope 自动发送 + SSE 处理 + TaskSelector task 切换按钮）
    - 组件拷贝：ChatInput / MessageBubble / MarkdownRenderer / ui/* / lib/utils / types/chat（从 web/ 拷贝）
    - 测试：12 个 vitest 用例（extract.test.ts + envelope.test.ts）
   - **所有后端改动测试**：+18 个测试用例，全量回归通过
    - **Bugfix: CORS 缺失导致 sidecar "连接断开"**（[issue 描述]：扩展跨源请求无 CORS 响应头，浏览器拦截响应体 → `sessionId` 变为 `undefined` → 所有后续请求路径含 `undefined` → sidecar 提示断开）
      - 服务端 `web_acceptor.py`：挂载 FastAPI CORSMiddleware（`allow_origins=["*"]`）
      - 扩展端 `backgroundClient.ts`：`getSession()` 校验 `error`/`sessionId` 后 reject，防止 `undefined` 静默传染
      - 扩展端 `background.ts`：`probeSession()` 拿到响应头后立即 `controller.abort()` 关闭 SSE 流
      - 测试：`test_web_acceptor.py` 新增 `TestCORS`（OPTIONS 预检、POST session、SSE 三种场景）
      - 文档：更新 `web-session-acceptor.md`（CORS 配置小节）+ `chrome-extension-impl-spec.md`（Services 节 CORS 说明）
- 2026-07-20 | **Chrome Extension 增强：Options 配置 + sidecar 已打开时选词重翻 + 右键菜单**
  - **Options 页面**：React + Tailwind 实现 server_url 配置表单（`chrome.storage.local` 持久化），默认 `http://localhost:8000`，URL 规范化（去尾斜杠、scheme 校验）；`config.ts` 改为 `getApiBaseUrl()` 异步函数
  - **已打开 sidecar 重翻**：background `action.onClicked` 发 `TRIGGER_TRANSLATE` 消息 → sidecar `runtime.onMessage` 监听 → 重新 `captureSnapshot` + `sendEnvelope`（task=translate）
  - **右键菜单**：manifest 加 `"contextMenus"` 权限；`onInstalled` 创建菜单项；`onClicked` 与图标点击共享 `triggerTranslate(tabId)` 路径
  - **sseClient**：`sendEnvelope` / `connectSSE` 改为接收 `baseUrl` 参数（由调用方通过 `getApiBaseUrl()` 获取）
- **测试**：+5 个 `normalizeUrl` vitest 用例
- **文档**：更新 `chrome-extension-spec.md`（§4 权限 + §10 未来优化）+ `chrome-extension-impl-spec.md`（§1 决策 / §2 目录 / §4 manifest / §7 config / §9 Services / 新增 §14 Options 与右键菜单）+ `extension/README.md`
- 2026-07-20 | **图标替换：占位图标 → `docs/arts/chrome-icon.png` 缩放版**
  - 从 `docs/arts/chrome-icon.png`（1254×1254 RGBA）缩放生成 16/48/128 PNG（保留 alpha）
  - `manifest.json` `action` 块增加 `default_icon` 显式声明工具栏图标
  - 更新 `chrome-extension-impl-spec.md` §2 目录注释 + §4 manifest 示例 + §13 Step 6 措辞
  - 重构建 `dist/` 生效
- 2026-07-20 | **Ctrl+C 无法退出 gateway --channel_web**：`WebSessionAcceptor.start()` 未设置 `timeout_graceful_shutdown`（默认 None），导致 SSE 长连接阻塞 shutdown 无限等待。在 `uvicorn.Config` 中加入 `timeout_graceful_shutdown=2.0`，超时后 uvicorn 自动 cancel 所有 task（含 SSE 生成器）→ 进程退出。补回归测试 `TestGracefulShutdown::test_timeout_graceful_shutdown_is_2_seconds` 断言配置正确。
- 2026-07-20 | **全局 side panel + tab 切换刷新内容**
  - 痛点：原 `open({ tabId })` per-tab 行为导致切 tab 时 panel 隐藏，每次需手动关开才能同步
  - 方案：`setPanelBehavior({ openPanelOnActionClick: true })` 全局 panel（切 tab 保持显示）+ sidecar 监听 `tabs.onActivated` 刷新 session/history
  - 代码改动：
    - `background.ts`：`onInstalled` 加 `setPanelBehavior`；移除 `action.onClicked`（被 `openPanelOnActionClick: true` 接管）；`triggerTranslate` 保留 `open({ tabId })` 供右键菜单用
    - `ChatWindow.tsx`：抽 `switchToTab()`（关旧 SSE → 查新 session → 加载 history → 连新 SSE）；加 `tabs.onActivated` 监听（带 `windowId` 过滤，仅同窗口）；init useEffect 改为调 `switchToTab()` + 首次 capture + auto-send
  - 文档同步：更新两个 spec 文档的 §5.2 打开流程、§5.3 tab 切换、§6 background、§14.2 触发翻译
  - 验证：`npm run build` 通过 + `npm test` 17 个单测全绿

- 2026-07-19 | **ADR**: 移除 Memory Extract Agent，Chat Agent 直接对接 Memory Writer Agent
  - `request_memory_extraction` 工具入参改为 `entries: list`（draft 仅含 LLM 字段：item_type/why_want_to_save_memory/title）
  - `MainAgent._pending_drafts` 替代 `_pending_extract`，支持一轮内多次工具调用累积
  - `MainAgent.invoke()` 末尾直接构造 MemoryEntry（补全系统字段）入队 Writer
  - 删除 `mem_extract_agent.py`；归档 `memory-extract-agent-spec.md`、`memory_extract_spec.md`
  - Chat Agent 通过按需 `vault_mcp_read(path="spec/memory_extract_output_spec.md")` 加载 entries 规范，不再静态注入 system prompt
  - 删除测试文件 `test_mem_extract_agent.py`；创建 `test_main_agent.py`（13 个用例）
  - 更新 `chat-agent-spec.md` / `memory-writer-agent-spec.md` / `chat-agent-tools-spec.md`
  - ADR 文档：`docs/ADR/20260719-remove_memory_extractor_agent.md`

- 2026-07-19 | **Bug 修复**：Chat Agent 无响应 — `dict` 下标访问 pydantic `_MemoryEntryDraft` 实例引发 `TypeError`
  - 根因：`request_memory_extraction` 工具按 `args_schema` 解析后产 pydantic 实例，`MainAgent.ainvoke()` 末尾用 `d["item_type"]`（dict 下标）访问，pydantic BaseModel 不支持 `__getitem__`
  - 修复：`agent.py` 改用属性访问 `d.item_type` / `d.why_want_to_save_memory` / `d.title`
  - `request_memory_extract.py`：`_MemoryEntryDraft` 字段类型收紧为 `Literal[...]`（与 ADR §4.1 对齐）
   - 测试用例从 dict 字面量改为 `_MemoryEntryDraft(...)` 实例，新增 `test_pydantic_drafts_regression` 回归测试
   - `session.py`：`_handle_user_message` / `_handle_system_notice` 包 try/except，ainvoke 异常不崩整个会话

- 2026-07-19 | **ADR**: 引入 `UserInputEnvelope` 统一结构化用户输入协议
  - 新增 `envelope.py`：`UserInputEnvelope` pydantic 模型（schema_version 1, task: translate/look_up/none, source tagged union: plain/web/pdf/epub/ios_app） + `wrap_plain_text()` + `render_envelope_to_message_text()`
  - `channel.py`：删除 `recv()` 抽象方法，新增 `recv_envelope()` 抽象方法
  - `stdio_channel.py` / `wechat_channel.py`：`recv()` → `recv_envelope()`，用 `wrap_plain_text()` 包装用户输入
  - `web_channel.py`：`recv()` → `recv_envelope()`，`_incoming` 队列类型改为 `UserInputEnvelope`
  - `web_acceptor.py`：`MessageBody` 改为 union（`text` / `envelope`），旧 `{text}` 自动包装
  - `session_events.py`：`UserMessage.text` → `UserMessage.envelope`
  - `session.py`：`_channel_listener` 调 `recv_envelope()`；`_handle_user_message` 渲染 envelope 后传给 `agent.ainvoke`；日志格式改为 `envelope={JSON}`
  - `agent.py`：system prompt 在 `## 用户意图分类` 前新增 `## 结构化用户输入（envelope）` 节
  - 新增 `tests/test_envelope.py`（14 用例）；更新 `test_web_channel.py` / `test_wechat_channel.py` / `test_web_acceptor.py` / `test_session_event_queue.py`
  - ADR 文档：`docs/ADR/20260719-envelope.md`；设计文档：`docs/impl-spec/envelope-spec.md`
  - 更新 `channel.md` / `session.md` / `chat-agent-spec.md` / `web-session-acceptor.md`

- 2026-07-19 | **用户交互日志**：在 Session 层记录所有用户输入与 Agent 回复文本（debug 级别，`[ChatAgent]` 前缀）
   - `session.py`：`_handle_user_message` 入口记 `[ChatAgent] IN`、出口记 `[ChatAgent] OUT`（逐条）；`_handle_system_notice` 同理记 `[ChatAgent] NOTICE IN` / `NOTICE OUT`
   - `session.md`：新增「交互日志」节，说明前缀、格式、日志级别
   - `observability.md`：在「Logging」节添加指引指向 session.md
   - `chat-agent-spec.md`：`Observability` 节增加用户交互 IO 日志的指引

 - 2026-07-16 18:52 | create_vault: 从只 copy spec/*.md 改为递归 copy templates/default/*（spec/*.md 走 compile_prompt，其余 raw copy）；返回字段 spec_written → files_written（int）；同步更新设计文档
 - 2026-07-16 18:59 | create_vault: spec/*.md 有 frontmatter 的原样 copy 保留 frontmatter，不再走 compile_prompt（compile_prompt 会剥离 frontmatter）；用 split_frontmatter 检测；补 spec/index.md 断言
 - 2026-07-16 21:15 | fix: _parse_write_confirmation 因 AIMessage.content 为 list 类型时报 AttributeError（list 无 .strip 方法）；添加 list→str 归一化处理并跳过空内容
 - 2026-07-16 22:04 | 排除 vault 中所有 index.md 文件不索引（vault 保留文件名，类别导航页 / wiki builder 临时根 index）；一并修复 CLI reindex 路径的内联 tmp/ 过滤改用 is_excluded_vault_file 统一收口，补上 spec/ 与 VAULT_SPEC.md 的 CLI 缺漏；同步更新设计文档
 - 2026-07-18 23:37 | 删除 Chat Agent「用户显式模式指定」功能（/dict /translate / /help 命令与 SystemMessage 注入）；联动删除 ExtractInput.intent_mode / MemoryEntry.user_intent / 下游 vault spec user_intent 字段；为后续 JSON 输入 UI 意图表达方案让路
 - 2026-07-18 23:37 | fix: test_mem_vault_search_embedding_store.py 中 _insert_one_doc 的 file_path 硬编码为 x.md 导致 UNIQUE 冲突，改为使用 ulid 生成唯一路径；test_wiki.py 中 test_generate_index_md 断言未匹配 _LANG_NAMES 新增的 emoji 前缀

- 2026-07-15 | tags 搜索全面升级：新增 `document_tags` 关系表精确匹配（AND/OR），替换旧 `d.tags LIKE` 子串过滤；新增 `tags_op` 参数；新增 `GET /{lang}/tags` 端点和 MCP `list_tags` 工具返回 tag 字典及计数；schema 升级至 v3，DB 升级后需 `reindex --rebuild` 回填表数据。
- 2026-07-15 | 同步更新 MCP 规范文档（`vault-mcp-spec.md`/`vault-mcp-spec-tools.yaml`）反映 `list_tags` 和 `tags_op`；更新 `search-api-spec.md` 添加 `tags_op` 请求字段描述；更新 `memory-vault-embedding-spec.md` knn 签名。
- 2026-07-15 | **LLM 调用可靠性加固**：`llm.py` 注入 httpx `AsyncClient` + `Client` 带 response event hook，非 JSON 响应体自动记录状态码与前 500 字节到 warning 日志；`agent.py` 新增 `_invoke_llm_with_retry`，对 `JSONDecodeError`/`httpx.HTTPError`/`InternalServerError`/`RateLimitError`/`APITimeoutError`/`APIConnectionError` 重试 2 次（指数退避），永久性错误（`AuthenticationError`/`BadRequestError` 等）透传不重试；重试耗尽返回 "AI 服务暂时不可用，请稍后重试" 友好提示。新增 `tests/test_agent_retry.py` 8 用例、`tests/test_llm_malformed_logging.py` 8 用例。
- 2026-07-16 | **Wiki 设计文档 + Spike 验证**：完成 Quartz 5 多语言 vault→wiki 方案的技术验证（临时测试 vault 跑通 en/ja 双语言 build + 子路径 SPA routing），确认 Quartz 5 全相对 URL 策略无需 `--baseDir`、`tmp/` 可经 `ignorePatterns` 排除、vault 根需注入临时 `index.md`。将 [wiki-spec.md](/docs/impl-spec/wiki/wiki-spec.md) 从讨论 stub 改写为正式设计文档，定稿选型（Quartz 5 + git submodule）、架构（独立进程，不复用 web-session-acceptor）、per-lang 独立 build、构建/服务流程、配置项、frontmatter 兼容性、搜索隔离、测试策略与未来演进。
- 2026-07-16 | **Wiki 模块实现 + build slug 修复 + 测试**：创建 `src/everlingo/wiki/` 模块（`builder.py`/`cli.py`）、`everlingo wiki build|serve` CLI 子命令、`tools/wiki/` 配置与 git submodule。修复 build 输出 slug 含 `content/` 前缀及错误包含 Quartz 框架文件的 bug（根因：`--directory` 指向 quartz 安装目录而非 `content/` 子目录）。新增 `tests/test_wiki.py` 8 个测试用例覆盖 content 清理、index 生成、root HTML 生成、多语言切换、无语言 vault 跳过与完整 build 流程。
- 2026-07-16 | **Wiki SPA 链接 404 修复 + spec 修正**：修复客户端渲染组件（explorer/graph/search）导航链接缺失 `/<lang>/` 前缀导致 404 的 bug。根因：`baseUrl` 的 pathname 决定 `<body data-basepath>`，空 pathname 使 `resolveBasePath(slug)` 产出 `/items/...` 而非 `/en/items/...`。实现：`_write_lang_config()` 用 PyYAML 按 lang 改写 `configuration.baseUrl = <host>/<lang>`。更新 `wiki-spec.md` 修正 spike 结论（第 229 行 `baseUrl` 不影响导航、第 236 行客户端渲染组件覆盖不足）。新增 `tests/test_wiki.py` 2 用例（`_write_lang_config`）。
- 2026-07-16 | **vault spec 源目录重命名：`vault_specs/default` → `templates/default/spec`**。目录 `src/everlingo/mem/vault/vault_specs/default/` 迁至 `templates/default/spec/`，`vault_specs/items/` 保持原位。改 5 处代码引用（`mcp_server.py` 常量+描述串、3 个测试文件包名），同步更新 7 个设计文档中路径/包名字串。存量 vault `spec/` 已落盘不受影响，仅影响 `create_vault` 播种源。139 测试全过。
- 2026-07-16 | **vault 知识点文件命名简化**：将知识点条目文件名格式由 `{slug}--{ulid}.md` 改为 `{slug}.md`。`ulid` 字段仍保留在 frontmatter 作为索引去重主键，仅从文件名移除。更新 `templates/default/spec/vault_spec.md`（格式定义、示例、目录结构、冲突处理说明）与 `mem_writer_agent.py` system prompt（新建条目步骤去掉"文件名 ulid 部分"，改为写入前 ls/search 检测同名冲突）。同步更新相关测试去掉 `--{ulid}` 文件名并将 `name.split('--')[0]` 取 slug 逻辑改为显式 `slug` 参数。运行时零影响（indexer 始终从 frontmatter 读 ulid）。
- 2026-07-16 | **Wiki serve 404 修复：`StaticFiles(html=True)` 不自动补 `.html` 扩展名**：Starlette 1.3.1 的 `StaticFiles(html=True)` 仅提供目录 `index.html` 解析和 `404.html` 回退，不会自动给无后缀 URL 追加 `.html`。新增 `WikiStaticFiles(StaticFiles)` 子类覆写 `lookup_path`，对无后缀路径尝试 `path + ".html"`。更新 `wiki_serve` 使用 `WikiStaticFiles`。更新 `wiki-spec.md` 修正对 `html=True` 能力的错误描述。新增 `test_wiki_static_files_html_mode` 测试用例。


- 2026-07-13 11:00 | 笔记编辑支持修改 Markdown Frontmatter（保护字段除外）
  - 保护字段：ulid / slug / type / created_at / timestamp / schema_version / first_seen / last_seen / seen_count（Writer 端强制保留原值，不信任 LLM）
  - 可编辑字段：title / description / description_in_target_lang / tags 等
  - MemoryEntry 新增 frontmatter 字段（可选 str）
  - memory_writer_action 工具新增 frontmatter 参数（完整 YAML 文本）
  - Writer 端 _edit_entry_async 实现 frontmatter merge 逻辑（保护字段强制保留 + 可编辑字段覆盖 + dump_frontmatter 重新序列化）
  - dump_frontmatter() 公开接口（frontmatter.py）
  - 审计事件 title 使用合并后的新值
  - 更新 agent.py system prompt 笔记编辑节（保护字段清单、编辑流程、确认话术说明）
  - 更新 3 个设计文档（chat-agent-spec.md / chat-agent-tools-spec.md / memory-writer-agent-spec.md）
  - 新增 4 项测试覆盖保护字段保留、可编辑字段合并、事件 title 更新、向后兼容

- 2026-07-13 10:00 | 补齐笔记删除/编辑功能的设计文档
  - chat-agent-spec.md：意图类型清单新增 #9 笔记删除 / #10 笔记编辑；重写「## 编辑笔记」节为「## 笔记删除与编辑」（含主流程、同步语义、约束、手工测试用例）；Agent tools 节新增 memory_writer_action 小节
  - chat-agent-tools-spec.md：新增「## 笔记删除与编辑 - memory_writer_action」工具集（operation/file_path/body 入参、返回 JSON、调用准则、同步实现机制、与 request_memory_extraction 的区别）
  - memory-writer-agent-spec.md：顶部补一句 delete/edit 不调 LLM；新增「## 笔记删除与编辑（同步 action 流程）」节（入口 execute_action_async、_ActionRequest、并发模型、delete/edit 路径、审计事件、不发 SystemNotice、离线降级、测试参考）
  - session.md：注明 delete/edit 不发 SystemNotice；修正 SystemNotice 字段名 headword→title
  - events_spec.md：补 action: edited 取值说明，并标注删除/编辑事件字段集与创建事件的差异
  - mem_entry_spec.md：补 delete/edit entry 来源说明与 title 占位语义

- 2026-07-12 19:30 | Memory Writer Agent system prompt 的 mem_entry_spec.md 加载方式从 PackageSource 改为 MCP compile_prompt（与 Extract Agent 一致）
  - 新增 `_load_mem_entry_spec_from_vault(lang)` 镜像 `_load_extract_spec_from_vault`
  - `_build_writer_system_prompt()` 改为取参数，不再本地编译 spec
  - `_write_kb_item_async` per-entry 调 MCP 加载 spec 后构建 prompt
  - 更新测试：新增 `mem_entry_spec_text` fixture、autouse `_patch_mem_entry_spec`
  - 更新 memory-writer-agent-spec.md 设计文档

- 2026-07-12 21:30 | Chat Agent 删除/编辑笔记条目（同步调用 Memory Writer Agent）
  - 数据结构扩展：mem_entry_spec.md 新增 operation / file_path / body 字段；events_spec.md 新增 action + file_path 字段；MemoryEntry 模型同步扩展
  - MemoryWriterAgent 新增 _ActionRequest + execute_action_async（public API）复用 daemon thread 串行执行 delete/edit，无锁
  - 新增 _delete_entry_async（stat→read→delete→events）和 _edit_entry_async（read→split frontmatter→write→events），纯代码无 LLM
  - 新增 _format_action_event_section / _append_action_event_async 记录 delete/edit 审计事件
  - _run_loop 新增 _ActionRequest 分发
  - 新建 memory_writer_action.py 工具工厂，Chat Agent 同步 await 调用
  - agent.py system prompt 新增"笔记删除与编辑"节（含确认流程约束）
  - _refresh_agent_if_needed 注入 memory_writer_action 工具
  - 13 项新增测试覆盖 delete/edit 核心流程与 daemon thread 分发

- 2026-07-12 17:00 | Chat Agent 显式驱动 Memory Extract Agent（而非每轮无条件触发）
  - 新增 `request_memory_extraction` 工具（tool def + factory），Chat Agent 通过 LLM 工具调用决定是否触发抽取
  - `ExtractInput` 新增 `reason` / `note` 字段，`WhySave` 新增 `Chat Agent 判定` 枚举
  - `MainAgent.invoke()` 改为条件 submit：工具调用设置 `_pending_extract` 标记，invoke 末尾统一切片提交
  - 未触发时游标仍推进，未触发轮自然成为后续 context_messages
  - Extract Agent 移除"应保存"语义筛选，改为信任上游 `reason` 映射为 `why_want_to_save_memory`
  - Extract Agent 保留结构性跳过规则（字数上限、来源边界、target_lang 无关）
  - system prompt 新增"记忆抽取触发"节，明确 LLM 何时调用工具
  - 更新 vault spec：`memory_extract_spec.md`（移除语义筛选）、`mem_entry_spec.md`（新增枚举值）
  - 更新设计文档：chat-agent-spec.md、memory-extract-agent-spec.md、chat-agent-tools-spec.md
  - 更新测试：新增 `test_no_tool_call_does_not_submit`、`test_pending_extract_triggers_submit`、`test_cursor_advances_even_without_submit`


- 2026-07-11 20:00 | Phase 1 — 更新 vault spec 文件：memory_extract_spec.md 去 stale 引用；events_spec.md 事件格式更新（headword→title, 移除 mean_summary）；创建 vault_specs/default/mem_entry_spec.md；memory_extract_output_spec.md 改用 {{ include }} 引用 mem_entry_spec.md
- 2026-07-11 20:00 | Phase 2 — 更新 mem_entries.py：LLMGeneratedEntry 输出字段改为 item_type/why_want_to_save_memory/title；MemoryEntry 改为 title + new_messages/context_messages（移除 headword/mean_summary/conversation_context）
- 2026-07-11 20:00 | Phase 3 — 更新 mem_extract_agent.py：MCP runtime 读取 vault spec（IndexerOfflineError 回退 PackageSource）；_post_process 填充 new_messages/context_messages/title
- 2026-07-11 20:00 | Phase 4 — 更新 mem_writer_agent.py：写 kb item 先于 events；_parse_write_confirmation 返回 (files, summary, conv_ctx)；_format_event_section 用 title+conversation_context；Writer system prompt 新增 conversation_context 生成指引
- 2026-07-11 20:00 | Phase 5 — 更新 session_events.py/gateway.py/agent.py：SystemNotice 和通知相关字段 headword→title
- 2026-07-11 20:00 | Phase 6 — 删除旧位置 mem/agents/mem_entry_spec.md 和 mem_extract_output_spec.md
- 2026-07-11 20:00 | Phase 7 — 更新测试：writer 测试 28/28 pass，extract 测试 29/29 pass，session_event_queue 12/12 pass，agent_system_notice 12/12 pass
- 2026-07-11 20:00 | Phase 8 — 更新设计文档 memory-extract-agent-spec.md 和 memory-writer-agent-spec.md 反映实现变更
- 2026-07-11 22:12 | 为 vault MCP Server 新增 compile_prompt 工具：展开 vault 内 markdown 文件的 {{ include }} 指令；更新 vault-mcp-spec.md（工具数 15→16、调试日志范围、分组说明）、vault-mcp-spec-tools.yaml（新增工具定义）、mcp_server.py（工具实现+Server Instructions 更新）、测试覆写 4 个用例
- 2026-07-11 23:00 | mem_extract_agent.py 改用 MCP compile_prompt 加载 spec：_load_extract_spec_from_vault 用 compile_prompt 替代 read，一次调用即可展开 include 链（memory_extract_spec.md → memory_extract_output_spec.md → mem_entry_spec.md）；移除 _load_extract_spec_from_package 与 PackageSource 兜底；修复 memory_extract_spec.md 缺少空行导致 include 未独立成段的问题；更新测试适配新签名与 mock；同步更新 memory-extract-agent-spec.md
- 2026-07-12 16:00 | 修复因 vault_spec.md 迁移至 vault_specs/default/ 导致的 3 个失败测试：test_mem_extract_agent.py 的 _demote_headings → shift_headings 导入修正、test_md_prompt_compiler.py 的 PackageSource 路径与内容断言更新、test_mem_vault_mcp_server.py 的 kb_items_spec.md → kb_items_spec_vocab.md 引用修正

- 2026-07-11 | Web Session Acceptor Session 超时回收机制：WebChannel 增加 DISCONNECT_GRACE（5 分钟无 SSE client）和 ABSOLUTE_IDLE_TIMEOUT（60 分钟绝对空闲）超时，recv() 返回 None 触发 QuitEvent；Gateway accept_session 加 done callback 清理 sessions 列表；web_acceptor create_session 加 done callback 清理 _channels；Session._channel_listener 加 QuitEvent 日志；WebChannel recv() 超时时输出 info 日志含 session id；测试 9 条（WebChannel 超时 5 条 + Gateway 清理 4 条）。
- 2026-07-07 (system-event-source) | Session/Chat Agent 系统事件源：新增 session_events.py（SessionEvent/SystemNotice/NoticeSink），Session 重构为事件队列模式（_channel_listener + post_event），MainAgent.ahandle_system_notice()，Writer system prompt 写入确认节 + _parse_write_confirmation + notify 到 Session，Gateway 路由桥（notify → post_notice → Session.post_event），测试 12 条用例。
- 2026-07-09 | Vault spec 布局改造：create_vault 改为将 vault_specs/default/*.md 逐文件 compile_prompt 后写入 $vault/spec/（而非单个 VAULT_SPEC.md 于 vault 根）；indexer is_excluded_vault_file 新增 spec/ 子目录排除规则；同步更新 agent 提示路径引用、vault_spec.md 自描述、spec 文档与测试。

- 2026-07-06 22:30 | Bug fix: grep / find 工具路径不存在时返回空结果而非 isError 报错（`mcp_server.py`），避免 Memory Writer Agent 在首次写入某子目录时因查重 grep 报错中断流程。同时更新 spec 文档与增加测试覆盖。
- 2026-07-06 23:00 | 修复 MCP Server 工具调用 debug 日志被 indexer 进程默认 `--log-level=info` 过滤未落盘的问题。`mcp_server.py:36` logger 名改为显式 `"everlingo.mem.vault.mcp_server"`；`server.py:534-536` log_config 追加独立 handler + 强制 DEBUG + 不 propagate，确保工具调用 debug 日志稳定写入 `indexer.log`。同步修 spec 中错误的目标文件（everlingo.log → indexer.log）。chat-agent 端发现 `voice_speak` 缺 `@log_tool_call` 装饰器，已补加。更新 `observability.md` 补充进程-日志边界说明。
- 2026-07-07 10:00 | 将本地 `mem_gen_id` ULID 工具从 `mem_writer_mcp_client.py` 迁移到 MCP Server（`mcp_server.py` 新增 `gen_id` 工具，workspace 级豁免 session.configure）；同步删除客户端本地实现，更新 `mem_writer_agent.py` system prompt 工具名与 `WANTED_TOOLS`；更新 spec 文档（`vault-mcp-spec.md`/`vault-mcp-spec-tools.yaml`/`memory-writer-agent-spec.md`）与测试覆盖。
- 2026-07-07 10:20 | 修复因 `mem_writer_agent.py` system prompt 修改（entry 标题变更、vault_spec 注释移除）导致的 6 个 unit test 失败：更新 `test_mem_writer_agent.py` 中对应断言以匹配当前 prompt 内容。
- 2026-07-07 11:00 | MCP fs 工具 path 兼容性改进：`resolve_vault_path()` strip 前导 `/` 与 `\`，将 `ls /` / `read /items` 等 Unix 风格路径视为相对 vault 根；同步更新 `vault-mcp-spec.md`、`vault-mcp-spec-tools.yaml`（中央注释 + path 字段描述），新增 2 个测试覆盖前导斜杠等价性与逃逸仍拒绝。

- 2026-07-06 | MCP Server 全部 14 个工具调用加入 debug 日志（tool name / input / output）：
  - spec `vault-mcp-spec.md` 新增独立节「工具调用 debug 日志」，约定格式、level、logger、不截断大字段、错误也记 debug
  - `mcp_server.py` 新增 `_log_mcp_tool` async 装饰器 + `_format_tool_params` 辅助函数（skip `ctx`），应用到全部 14 个工具
  - 已有 20 例测试全部通过，无回归
  - 改动：`src/everlingo/mem/vault/mcp_server/mcp_server.py` ; `docs/impl-spec/vault-mcp/vault-mcp-spec.md`
- 2026-07-06 | 迁移 Memory Writer Agent 从本地 fs 工具到 Vault MCP Server：
  - MCP server `write` 工具新增 frontmatter 归一化（防 LLM 写坏 YAML 致下游解析失败）
  - 新增 `src/everlingo/mem/agents/mem_writer_mcp_client.py`：`mcp_vault_connection` per-entry 异步上下文 + 客户端 `mem_gen_id` ULID 工具 + `IndexerOfflineError`
  - `mem_writer_agent.py` 改 async（per-entry `asyncio.run`），`mcp_vault_connection` 包 per-entry MCP stream + `session.configure`；`_append_event_async` 通过 MCP `stat`+`write`/`append` 实现；`_process_batch` 捕获 `IndexerOfflineError` 丢弃 entry + `logger.error` 告警
  - 删 `src/everlingo/mem/agents/mem_writer_tools.py`（mem_* 工具沙箱、frontmatter 归一化、post-write hook 全部迁出或废弃）
  - `gateway.py` 删除 `_SearchClientProxy` / `search_client` 单例与 post-write hook 链路（MCP server 与 indexer 同进程，watcher 自动重索引）
  - system prompt 工具名一次性切到 MCP 名（`read`/`write`/`grep`/`find`/`ls`/`append`/`delete`），保留 `mem_gen_id`；增加 session.configure 自动设置说明
  - 新增 `pyproject.toml` 依赖 `langchain-mcp-adapters>=0.3.0`（官方适配，`MultiServerMCPClient` 异步上下文 + `load_mcp_tools`）
  - `tests/conftest.py` 新增 `tmp_mcp_workspace` / `mcp_inmem_server` 共用 fixture（in-memory FastMCP transport 替换 `mcp_vault_connection`）
  - 重写 `tests/test_mem_writer_agent.py`（32 用例）：ULID / events 路径 / system prompt（MCP 工具名） / writer 流程（per-entry ainvoke）/ lang 注入 / indexer 离线降级 / daemon 线程 / gateway 单例代理
  - 删 `tests/test_gateway_search_hook.py`（hook 链路消失）、`tests/test_mem_writer_search_integration.py`（post-write 路径已废）
  - 改动：`src/everlingo/mem/vault/mcp_server/mcp_server.py` ; `src/everlingo/mem/agents/mem_writer_agent.py` ; `src/everlingo/mem/agents/mem_writer_mcp_client.py` (新) ; `src/everlingo/gateway/gateway.py` ; `pyproject.toml` ; `tests/conftest.py` (新) ; `tests/test_mem_vault_mcp_server.py` ; `tests/test_mem_writer_agent.py` ; `docs/impl-spec/memory-writer-agent-spec.md`
- 2026-07-06 | `session.configure` 自动创建缺失的 lang vault：
  - `session.configure` 在 `lang` 不在 `workspace.lang_dirs()` 时内部调 `create_vault_tool` 自动创建 vault；创建失败（含非法 lang 名）返回 `isError=true` + `auto-create vault failed` 错误文案
  - `create_vault_tool` 的 invalid lang 名校验自然透传（`"a/b"` / `"."` / 空 / NUL 等）
  - `_SERVER_INSTRUCTIONS` 同步更新（点 3 文案）
  - spec 文档更新：`vault-mcp-spec.md`「lang 合法性」节、`vault-mcp-spec-tools.yaml` `session.configure.lang` description
  - 测试更新：`test_session_configure_invalid_lang` 改用非法名 `"a/b"`；新增 `test_session_configure_auto_creates_vault` / `test_session_configure_auto_create_failure_propagates`；`test_session_reconfigure_switches_lang` 去掉手动 `mkdir` 依赖自动创建
  - 改动：`src/everlingo/mem/vault/mcp_server/mcp_server.py` ; `docs/impl-spec/vault-mcp/vault-mcp-spec.md` ; `docs/impl-spec/vault-mcp/vault-mcp-spec-tools.yaml` ; `tests/test_mem_vault_mcp_server.py`
- 2026-07-06 | 修复 `mcp_vault_connection` 未检查 `session.configure` 返回 `isError` 的 Bug：
  - 根因：MCP `ClientSession.call_tool` 在服务端返回 `isError=True` 时不抛异常；`session.configure` 失败（如 `lang` 不在 `workspace.lang_dirs()`）时 `sess.lang` 未被设置但客户端继续 `load_mcp_tools` 并 yield tools；agent 调 `grep` 时服务端抛误导性 "session not configured: call session.configure first"，真实原因（"lang not found in workspace: xx"）丢失
  - 修复：configure 返回后检查 `isError`，失败抛 `IndexerOfflineError`（携带 `content[0].text`）。`mcp_vault_connection` 不再 yield tools，避免后续 `grep` 走到 `_require_session` 的失败分支
  - 调用方现有 `except IndexerOfflineError` 路径会 `logger.error` 记录真实原因并丢弃 entry
  - 改动：`src/everlingo/mem/agents/mem_writer_mcp_client.py`

 - 2026-07-06 | vault-mcp-spec-tools.yaml 全 12 工具补 outputSchema（JSON Schema 2020-12）：session.configure/ls/read/write/append/grep/find/stat/mkdir/delete/tree/search；search 的 chunk 用 oneOf [null, object]；tree 用 $defs/TreeEntry 递归引用处理嵌套。jsonschema Draft202012Validator.check_schema 全部通过。
 - 2026-07-06 | vault-mcp-spec.md「示例」节补 search 工具 MCP 工具返回结构（content + structuredContent envelope）：完整 tools/call 响应 JSON（含 jsonrpc 2.0、id、result.content[0].text、result.structuredContent、isError），附要点（text MUST 等于 json(structuredContent) 的向后兼容约束、isError 错误响应、其它工具 outputSchema 详见 yaml）。验证：text 严格等于 json.dumps(structuredContent)、structuredContent 包含 outputSchema 全部 required 字段、jsonschema.validate 全部通过。
 - 2026-07-06 | 设计 indexer 内嵌 MCP Server（方案 C 合并部署）spec 文档（仅文档，未改代码）：vault-mcp-spec-tools.yaml 新增 `session.configure` 工具（设定会话默认 lang + interface_language，stream 级生命周期，未 configure 时所有工具报错）+ 重写 `search` 工具（删 topK→limit，加 q/lang/kind/item_type/tags/mode/limit，mode 默认 hybrid，description 嵌入精简版示例 3 与 hits 字段说明）+ fs 节加会话 lang 共享注释；vault-mcp-spec.md 重写：新增「部署形态」（MCP server 内嵌 indexer 进程，URL 写 indexer.mcp.url）「会话 lang 机制」（session.configure + 强制显式 + 可重调切换 + stream 级 + 进程内 dict）「与 indexer 的关系」（search 工具进程内直调 do_search 不经 HTTP/UDS；fs 工具纯文件操作；同进程无不可达降级）「示例」节（完整转引 search-api-spec.md 示例 3 含 chunk 字段说明）；workspace.md 补 indexer.mcp.url 行注释；memory-vault-search-spec.md 进程拓扑 ASCII 图补 MCP Server 内嵌块 + 模块布局加 mcp_server.py。决策：方案 C 合并部署（agent 只连一个 MCP server）；search lang 工具参数可选+会话默认；入参全暴露；示例双处呈现（工具 description 精简版 + spec.md 完整版）；未 configure 用策略 A 报错；session.configure 暴露 lang + interface_language；state stream 级不持久化。

 - 2026-07-05 | 修复 test_injected_spec_headings_nested_under_parent 断言过时的标题文本：`vault_spec.md` 的 h1 在 per-lang 重构（commit 36f26cd）从 `# Memory Vault Runtime Spec` 改为 `# 单语言 Memory Vault Spec`，但该测试未同步更新。修改 `tests/test_mem_writer_agent.py:455-477`：docstring 注释 + 第 464 行正向断言 + 第 472 行反向 h1 断言全部从旧英文标题改为 `单语言 Memory Vault Spec`。440 tests pass。

 - 2026-07-05 | 实现 per-lang vault/index 重构的源代码更新（14 文件）：workspace.py 新增 lang_vault_dir/lang_index_dir/index_db_path(lang)/lang_dirs；schema.sql 删 lang 列+idx_doc_lang_type；events_index.py 新路径模式+parse_file/parse_kb_item_path 加 lang 参数；indexer.py parse_file(absolute, memory_root, lang)+INSERT/UPDATE SQL 删 lang；search.py lang 必填+SQL 删 d.lang；sync.py reconcile 加 lang 参数+跳过 tmp/；protocol.py SearchHit.lang:str+LangStatus+StatusResponse；client.py lang 参数+/{lang}/路由；server.py LangState+AppState 多 DB 架构；cli.py reindex LANG/embed LANG；embedding/store.py knn_with_filter 删 lang；watcher.py VaultWatcher 加 lang 参数；mem_writer_tools.py set_current_lang+hook(lang,path,op)+_memory_root 用 lang_vault_dir；mem_writer_agent.py _events_rel_path 去 lang 前缀+_append_event 用 lang_vault_dir+传 lang 给 _fire_post_write。
 - 2026-07-05 | vault frontmatter 字段对齐 Google OKF spec：`vault_spec.md` 删除「Markdown Frontmatter 通用字段」节，通用字段合并到 `kb_items_spec.md` 的「增加 Markdown Frontmatter 字段」节；`updated_at`→`timestamp`（OKF 标准槽位，ISO 8601）；`intro_in_interface_lang`→`description`（OKF 标准槽位）；`intro_in_target_lang`→`description_in_target_lang`（vault 扩展键，保留对称命名）；5 个 item_type 子章节 frontmatter 示例与 2 处 slug 规则文本同步。代码：`schema.sql` documents + documents_fts 两列 rename（列序不变，bm25 权重不变）；`indexer.py` ParsedDoc 字段、parse_file 键名、INSERT/UPDATE/FTS SQL、rebuild_fts SQL 与 fm_fields label、init_db schema_version "1"→"2"；`search.py` bm25 权重列序注释；`frontmatter.py` 顶部注释；`mem_writer_agent.py` system prompt 注释。测试：`test_mem_vault_search_indexer.py` 含 schema_version 断言 "1"→"2"`test_mem_vault_frontmatter.py`、`test_mem_writer_agent.py` raw 字符串与断言键名同步。impl-spec：`memory-vault-search-spec.md`（DDL 2 处+frontmatter chunk 说明+纯单语字段注释）、`memory-vault-embedding-spec.md` frontmatter 字段列表。决策：events 文件仍无 frontmatter（OKF §9 conformance 已知 gap 另开任务）；不写数据迁移（用户确认数据可清空，删除旧 .sqlite 重建）；`search.drawio.svg` 不改；`docs/planning-discuss.md` 与 `docs/archived/archived-task.md` 保留历史字段名引用。439 tests pass。
 - 2026-07-05 | 更新全部测试文件适配 per-lang 重构（15 文件，432 tests pass）：test_mem_vault_search_indexer.py 重写（parse_file+lang 参数+无 lang 列断言）；test_mem_vault_search_sync.py reconcile 加 lang+路径去 lang 前缀；test_mem_vault_search_search.py do_search 加 lang+路径去 lang 前缀；test_mem_vault_search_embedding_store.py 删 lang 过滤测试+INSERT SQL 删 lang；test_mem_vault_search_client.py index_file/delete_file/rebuild 加 lang；test_mem_vault_search_server.py AppState 多 DB+路由 /{lang}/...+status 聚合；test_mem_writer_search_integration.py hook(lang,p,op)+set_current_lang；test_workspace_index.py 新增 lang_index_dir/lang_vault_dir/indexer_socket_path 测试；test_mem_vault_search_watcher.py VaultWatcher 加 lang；test_mem_vault_search_embedding_search.py lang 参数+路径去 lang 前缀；test_mem_writer_agent.py _events_rel_path 去 lang 前缀+tmp_memory 用 lang_vault_dir。
 - 2026-07-05 | 从 Memory Vault 全文搜索设计中删除 USER.md 索引对象（kind='user'）：移除索引对象分类、schema 注释枚举、search-api-spec 枚举、indexer USER.md 分支、events_index.is_user_file()、protocol.py Literal 枚举、相关测试；保留偏好文档 USER.md（非 vault 索引对象）
 - 2026-07-05 | 更新 spec 文档以反映 per-lang vault/DB 重构（仅文档，未改代码）：workspace.md 增「下游影响」「数据迁移」小节并修正「语义搜索」措辞；memory-vault-spec.md 路径改为 `$workspace/memory/languages/$lang/vault/`；vault_spec.md 目录结构改为 per-lang + tmp/ per-lang；memory-vault-search-spec.md 进程拓扑改为单 indexer 持 N 个 lang DB、DB 文件位置表、schema 删 `documents.lang` 列与 `idx_doc_lang_type` 索引、file_path base 改为 lang vault 根、watcher 多根 + 排除 tmp/、reconcile 多 lang、SearchClient.search 的 lang 改必填、SearchHit.lang 改 str、CLI 加 LANG 参数、indexer.sock 移到 `$workspace/`；memory-vault-embedding-spec.md EmbeddingWorker 改单 worker 轮询 N 个 conn、meta per-lang、store.knn 删 lang 过滤、per-lang 降级；search-api-spec.md 端点加 `/{lang}/` 路由、socket 路径改 `$workspace/indexer.sock`、file_path 去掉 `{lang}/` 前缀、`GET /status` 改聚合响应；memory-writer-agent-spec.md mem 工具 cwd 改为 `$workspace/memory/languages/$lang/vault/`。决策：删 lang 列/索引、lang=None 拒绝、不提供数据迁移、indexer.sock 放 `$workspace/`、单 worker 轮询、tmp/ per-lang。
 - 2026-07-05 | 修复 kb item 写入路径错误（写到 memory/vault/en/... 而非 memory/languages/en/vault/...）：mem_writer_agent._write_kb_item 注入 set_current_lang(entry.lang)+finally reset；_memory_root 改 raise 取消旧布局静默降级；system prompt 路径表述去 $lang/ 前缀（items/、events/ 相对 lang vault 根）；test_mem_writer_agent 修断言路径+新增 lang sandbox 回归测试；附带清理 main.py 帮助文本与 watcher.py 注释的旧布局表述。
 - 2026-07-05 | 修复 indexer 启动后新增 lang 不会自动开 DB + 修复 gateway 写后钩子签名错误：server.py 加 LangDiscoveryWatcher（recursive 监听 memory/languages/，仅响应 */vault/ 目录 on_created） + AppState._open_lang() 加锁懒加载（vault 目录存在为前提） + _get_lang_state miss 时调 _open_lang；gateway.py _hook(rel,op) 2-arg 改 3-arg (lang,path,op) 匹配协议 + index_file/delete_file 改传 (lang,path)；test_mem_vault_search_server.py 新增 3 用例（lazy_open / 缺 vault 404 / discovery_watcher）；test_gateway_search_hook.py 新建 3 用例（hook 转发 index/delete/socket path）；spec 文档 memory-vault-search-spec.md 加「运行时新 lang 发现」节 + 数据流 + 进程拓扑图补 LangDiscoveryWatcher，workspace.md 下游影响 reconcile 条款补运行时发现说明；440 tests pass。
 - 2026-07-06 | 实现 indexer 内嵌 MCP Server（方案 C）：pyproject.toml 加 fastmcp>=2.0（实际 3.4.3，API 兼容 spec 描述的 add_tool/http_app(streamable-http)）；src/everlingo/workspace.py 新增 indexer_mcp_url_path() 返回 $ws/indexer.mcp.url；新建 src/everlingo/mem/vault/mcp_server/ 子包（__init__.py + mcp_server.py，mcp_server.py 618 行），导出 create_mcp_app/run_mcp_server/pick_free_port/SessionState/SessionRegistry/PathEscapeError/resolve_vault_path；SessionRegistry 按 MCP session id 索引，进程内 dict，stream 关闭即丢；resolve_vault_path 用 Path.resolve()+is_relative_to 校验 ../ 逃逸；注册 12 工具（session.configure/ls/read/write/append/grep/find/stat/mkdir/delete/tree/search）严格对齐 vault-mcp-spec-tools.yaml 的 inputSchema/outputSchema；未 configure 调 fs/search → RuntimeError(_SESSION_NOT_CONFIGURED_MSG) → FastMCP 包装为 isError=true；search 工具进程内直调 search.search(conn, lang=..., embedder=ls.embedder, ...) 共享 AppState；uvicorn.run 在 daemon 子线程跑（mcp_server.run_mcp_server），主线程保留原 FastAPI UDS；_run_indexer 新流程：pick_free_port("127.0.0.1")→写 indexer.mcp.url→构造 AppState→create_app(state)→起 MCP daemon 线程→主线程 uvicorn.run(app, uds=...)→finally unlink mcp.url；tests/test_mem_vault_mcp_server.py 8 用例：未 configure 报错 / invalid lang / configure+ls+read+write / 路径逃逸拒绝 / hybrid search 命中（watcher 5s 轮询）/ lang 参数覆盖会话（跨 ja）/ 重调切换 lang 落点正确 / content[0].text==json.dumps(structured_content, separators=(",", ":"))；用 _McpClientContext 包装 FastMCP in-memory Client（同一 asyncio.run 内 enter Client+跑 body 解决 session 绑 loop 问题）；spec 增量：vault-mcp-spec.md 加「实现细节」节（绑 127.0.0.1+OS 端口/daemon 子线程/fastmcp 3.x 实际版本/Error 前缀不破坏可读性），memory-vault-search-spec.md 模块布局改 mcp_server/ 子包。448 tests pass（440→448）。决策：mcp_server 独立子包（与 search/ 平级，因含 fs+search+session 三类工具）；子线程并发（vs asyncio 同 loop）；OS 端口（vs 固定配置）；FastMCP 自动包 text+structuredContent（手工重复无意义）；保证 text==json.dumps(structured_content, separators=(",", ":"))（FastMCP 用紧凑分隔符）。


- 2026-07-05 12:00 | Memory Vault 目录结构调整：vault 文件从 `$ws/memory/*` 迁移到 `$ws/memory/vault/`，索引目录从 `$ws/index/` 迁移到 `$ws/memory/vault_index/`。改动：`workspace.py` 新增 `vault_dir()`，`index_dir()` 返回值改为 `memory/vault_index`；`mem_writer_tools.py`、`mem_writer_agent.py`、`search/cli.py`、`search/server.py` 中 vault 文件操作改用 `vault_dir()`；更新测试 `test_workspace.py`、`test_workspace_index.py`、`test_mem_writer_agent.py`；更新文档 `vault_spec.md`、`memory-vault-search-spec.md`、`search-api-spec.md`、`memory-writer-agent-spec.md`。
- 2026-07-05 00:00 | 修正 `documents.lang` 数据来源：从 Markdown Frontmatter `lang` 改为 vault 文件路径前缀 `{lang}/`（如 `en/items/...` → lang=en）。改动：`events_index.py` 新增 `KbItemFileMeta` + `parse_kb_item_path()`；`indexer.py` kb item 分支用 path 解析 lang（frontmatter `lang` 字段忽略），USER.md 分支 lang=None；更新 `test_mem_vault_search_indexer.py`（修正 2 处断言 + 删 2 处冗余 frontmatter lang + 新增 2 个测试）；`memory-vault-search-spec.md` schema 注释补「来源：vault 文件路径前缀」。
- 2026-07-04 00:00 | 向量检索增加 Markdown Frontmatter 字段 chunk：`indexer.py` 新增 `_frontmatter_chunks()`，为 `kind='item'` 的 `headword`/`title`/`intro_in_interface_lang`/`intro_in_target_lang` 各生成一个 `section_kind='frontmatter'` 的 chunk（`chunk.text = "key: value"`，`char_offset=NULL`），排在 body chunk 之前；同步更新 `rebuild_fts()`；更新 `memory-vault-search-spec.md` 与 `memory-vault-embedding-spec.md`；新增 7 个测试于 `test_mem_vault_search_indexer.py`。
- 2026-07-01 16:50 | 封装 AIEmbedding (langchain OpenAIEmbeddings + OpenRouter)；新增 OPENAI_EMBEDDING_MODEL 配置；编写 4 个单测 + 2 个集成测试，全部通过（已实际调通 OpenRouter embedding 端点）
- 2026-07-01 17:45 | 落地 memory vault 语义向量检索：新增 sqlite-vec 依赖；embedding/store.py（vec0 虚表 + KNN + 模型作废 + sync）；embedding/worker.py（后台守护线程 + 批嵌入 + 退避重试）；search.py 增 _vec_recall/_hybrid_recall(RRF) 路由 mode='semantic'/'hybrid'；indexer.index_file 加 content_hash 短路稳定 chunk_id；sync.open_db 加载 sqlite-vec 失败降级；server.py 接 worker + POST /embed 端点 + /status 增 embedded_chunks/embedding_model_id；cli.py 增 `everlingo mem embed` 子命令；新增 27 个单测覆盖 store/worker/search 三个模块，全部通过（总测试 422 个通过）
- 2026-07-01 15:30 | 修复 LLM Writer 写出近似但非法 YAML 导致 indexer 跳过 kb item 的 warning：`src/everlingo/mem/vault/frontmatter.py` 新增 `split_frontmatter` / `tolerant_parse`（先 yaml.safe_load，失败回退逐行 key:value 解析；已知 list 字段空值归一为 `[]`，`seen_count`/`schema_version` 转 int）/ `parse_frontmatter` / `normalize_frontmatter_text`（`yaml.safe_dump` + `sort_keys=False` + `default_flow_style=False` + `width=4096` 重序列化）。`src/everlingo/mem/vault/search/indexer.py` 删除本地 `_FRONTMATTER_RE`/`_parse_frontmatter` 改 import 新模块（3 处调用点）。`src/everlingo/mem/agents/mem_writer_tools.py:mem_write_file` 写盘前调 `normalize_frontmatter_text` 把 LLM 落盘内容归一为合法 YAML。`src/everlingo/mem/vault/kb_items_spec.md` 3 处含特殊字符的示例值（pragmatics 42 行 / vocab 123-125 行 / phrase 209-211 行）改为单引号包裹的合法 YAML 范例。就地修复 4 个已落盘畸形文件（`en/items/vocab/god--...md` / `ufo--...md` / `en/items/grammar/for-vs-since--...md` / `subject-verb-agreement-...md`）：frontmatter 归一化、body 段字节不变，下一次 indexer 对账即入索引。`docs/impl-spec/search/memory-vault-search-spec.md` 新增「frontmatter 容错解析」小节。新建 `tests/test_mem_vault_frontmatter.py` 14 例（4 个 log 真实 case + 严格 YAML passthrough + 列表/整型/无 frontmatter passthrough + normalize body 不变）；扩展 `test_mem_vault_search_indexer.py` 3 例容错 parse_file；扩展 `test_mem_writer_agent.py` 1 例 `test_write_normalizes_malformed_frontmatter`（断言落盘 frontmatter 严格 yaml.safe_load 成功且 body 段不变）。`pytest` 全量 384 例通过，无回归。
 - 2026-07-01 15:05 | 修复 fugashi/unidic 初始化失败导致日文退化为字符切分：`src/everlingo/mem/vault/search/tokenizer.py` `_load_fugashi` 仅传 `-d <dicdir>` 给 `fugashi.GenericTagger`，MeCab 在查找默认系统 rc 文件 `/usr/local/etc/mecabrc`（此环境不存在）时报 `param.cpp(69) [ifs] no such file or directory`，触发连锁两个 warning（`unidic 不可用` + `fugashi fallback 也失败`）。改为 `fugashi.GenericTagger(f'-r "{dicdir}/mecabrc" -d "{dicdir}"')`，用 unidic dicdir 内自带的 dummy `mecabrc` 显式指定 rc 文件，向后兼容。验证：tagger 成功加载（`<GenericTagger object>`）、`tokenizer_version()` 含 `unidic:unknown`、`tests/test_mem_vault_search_tokenizer.py` 10 例全通过、indexer 重启后日志（2026-07-01 14:03:06 段）不再出现上述 warning（旧 log 顶部仍残留修复前的 stale 记录）。无新依赖、无 schema 变更，无需 FTS 重建。
 - 2026-07-01 14:20 | 将 `everlingo mem indexer start` 从后台守护子进程改为当前进程前台运行：`cli.cmd_indexer_start` 原用 `subprocess.Popen(..., start_new_session=True)` 拉起 `python -m uvicorn --factory ...` 子进程并轮询 `/status` 就绪后返回；现改为直接在当前进程调用 `server._run_indexer(log_level, log_path)`，阻塞式 `uvicorn.run(app, uds=...)`，Ctrl-C 退出。日志仍写 `$workspace/logs/indexer.log`，通过 `logging.config.dictConfig` 构造 FileHandler 作为 `uvicorn.run(log_config=)` 注入（覆盖 root/uvicorn/uvicorn.error/uvicorn.access，propagate=False）。`server._run_indexer` 签名扩展为 `(log_level, log_path=None) -> int`，返回 0。删除 cli.py 中 `subprocess`/`os`/`time` import 与轮询循环、env 注入、子进程 stdout/stderr 重定向；保留 socket 存在时探活与孤儿 socket 清理。`main.py`/`cli.py` build_parser 中 `indexer start` help 文案由「启动 indexer 守护进程」改为「前台启动 indexer（阻塞，Ctrl-C 退出）」。同步更新 `docs/impl-spec/search/memory-vault-search-spec.md`：进程拓扑标题改为「独立 indexer 进程」并新增前台运行说明段，「为什么独立进程」新增「前台进程，用户自管后台化」要点，`indexer start` 行为表与 CLI 命令示例、「与现有架构的契合」小节相应措辞由「守护进程」改为「前台进程」。测试 `tests/test_mem_vault_search_cli.py`（未覆盖 start）+ `test_mem_vault_search_client.py` 全部通过 8 例。
 - 2026-07-01 13:05 | 修复 `everlingo mem indexer start` 启动失败：原 `cmd_indexer_start` 子进程用 `python -m uvicorn everlingo.mem.vault.search.server:run_server --uds ...` 缺 `--factory` 参数，uvicorn 把 `run_server` 当 ASGI app 调用，但 `run_server` 是有 3 个 positional 参数的函数，触发 `Error loading ASGI app factory: run_server() missing 3 required positional arguments`；且即便加了 `--factory`，旧实现里 `run_server` 仍调用 `uvicorn.run()` 触发 `asyncio.run() cannot be called from a running event loop`（因为 uvicorn 自己已在事件循环里）。重构 `server.py`：新增顶层 `run_server() -> FastAPI` 作为 uvicorn factory（零参，从 `EVERLINGO_WORKSPACE_DIR` env 读 ws 路径，构造 `AppState` 后返回 `create_app(state)`）；新增 `_run_indexer(log_level)` 给 `cli.cmd_indexer_start` 走直接 `uvicorn.run()` 而非子进程调用；`cli.cmd_indexer_start` 子进程命令补 `--factory` 参数。同时确认 unidic 词典已下载（CI 步骤 `python -m unidic download` 是 spec 已要求的；本地 venv 首次已下载 526MB unidic 词典到 `site-packages/unidic/dicdir/`）。手动验证：`everlingo mem indexer start` / `status` / `reindex` / `reindex --rebuild` 端到端通过（用 `/tmp/test-everlingo-ws` 临时 workspace 跑通；默认 workspace 的残留 `index/indexer.sock`+`index/memory.sqlite`+`logs/indexer.log` 已清理）。
 - 2026-07-01 12:30 | Memory Vault 全文搜索落地：实现 `docs/impl-spec/search/memory-vault-search-spec.md` 全期 FTS 范围。新增 12 个模块于 `src/everlingo/mem/vault/search/`（`__init__.py` / `schema.sql` / `tokenizer.py` / `indexer.py` / `events_index.py` / `search.py` / `sync.py` / `watcher.py` / `server.py` / `protocol.py` / `client.py` / `cli.py`），新建 `src/everlingo/mem/vault/__init__.py`；`workspace.py` 新增 `index_dir()` / `index_db_path()` / `indexer_socket_path()` 三个访问器；`pyproject.toml` 新增 `watchdog` / `jieba` / `fugashi` / `unidic` / `httpx` 五个依赖（unidic 词典需 `python -m unidic download` 单独下载，indexer 启动时检测到空词典会降级为字符切分并 warn）；`main.py` 改造为 argparse subparsers（`everlingo mem ...` / `everlingo gateway ...`，无子命令时保持 stdio gateway 行为，向后兼容），`gateway.py` 抽出 `_parse_args` / `_run` 供两个入口共享；Writer 集成：新增 `mem_writer_tools.set_post_write_hook(callable)` 注入接口，`mem_write_file` / `mem_append_file` / `mem_remove_file` 写后 fire-and-forget 触发钩子，`_append_event` 写后同样触发；`gateway.py` 新增 `_SearchClientProxy` 进程级单例（懒构造，与 `memory_writer` 模式一致），首次访问时构造 `SearchClient(uds_path)` 并把 `index_file` / `delete_file` 包装为钩子注入 Writer。Schema 用 `documents` / `documents_fts`(unicode61+body_raw UNINDEXED) / `chunks` / `chunk_embeddings`(空) / `meta`；`init_db` 写 `tokenizer_version` + `schema_version`；`reconcile` 启动时扫 vault 比 `file_mtime`+`content_hash` 补漏清孤儿，tokenizer 版本变化时清 `documents_fts`+`chunks` 全量重建（`rebuild_fts`）；`watcher.VaultWatcher` watchdog 监听 300ms 去抖，ulid 幂等 upsert，重命名时 src 删 + dest upsert；`server.run_server` uvicorn `--uds $ws/index/indexer.sock` + FastAPI 5 端点（POST /search, POST /index, POST /delete, POST /rebuild, GET /status），lifespan 触发对账+启动 watcher；`search` bm25 加权（headword/title 10，其它 1~4），query 先 `tokenize_for_fts_query` 包裹为 phrase query 规避 FTS5 语法冲突；`client.SearchClient` httpx HTTPTransport(uds=) unix socket，indexer 不可达时 `search()` 降级返回 `[]`+warning、`index_file()/delete_file()` 降级返回 `False`+warning、`status()/rebuild()` 返回 `None`+warning；SQLite 连接启用 WAL + foreign_keys=ON + check_same_thread=False（兼容 TestClient / uvicorn worker 线程）。新增 9 个测试文件（`test_workspace_index.py` / `test_mem_vault_search_tokenizer.py` / `test_mem_vault_search_events.py` / `test_mem_vault_search_indexer.py` / `test_mem_vault_search_search.py` / `test_mem_vault_search_sync.py` / `test_mem_vault_search_client.py` / `test_mem_vault_search_server.py` / `test_mem_vault_search_watcher.py` / `test_mem_vault_search_cli.py` / `test_mem_writer_search_integration.py`）共 67 个新 test，`.venv/bin/pytest` 366 个 test 全部通过。
 - 2026-07-01 11:18 | workspace 目录支持指定任意路径：新增 `workspace.init_workspace_dir(path)` 与 `_current_ws_dir` 进程级状态，`current_workspace()` 解析优先级扩展为 `init dir > EVERLINGO_WORKSPACE_DIR > init name > EVERLINGO_WORKSPACE > default`；`main.py` 新增 `--workspace-dir` CLI 参数并与 `-w/--workspace` 通过 `add_mutually_exclusive_group` 互斥；`tests/test_workspace.py` 新增 6 个 dir 相关测试（覆盖 dir 覆盖 name、env dir 覆盖 env name、None 重置、~ 展开、init dir 覆盖 env dir、访问器跟随 dir），fixture 补 `delenv("EVERLINGO_WORKSPACE_DIR")`；`docs/impl-spec/worksplace/workspace.md`「Workspace 选择机制」小节重写为 5 级优先级并补充 `--workspace-dir` / `EVERLINGO_WORKSPACE_DIR` 互斥规则与示例
 - 2026-06-29 21:49 | 重构 Memory Extract Agent system prompt：将「输出 schema / 字段说明与真实性约束 / 输出格式」三段抽离至 `src/everlingo/mem/agents/mem_extract_output_spec.md`，改用 `md_prompt_compiler` 的 `PackageSource` + `compile_prompt` 加载，与 Memory Writer Agent 加载 `vault_spec.md` 机制一致；同步更新设计文档 `docs/impl-spec/memory-extract-agent-spec.md` System prompt 要点 / Prompt 文件加载 一节
 - 2026-06-30 | Memory Writer Agent system prompt 增加「语言配置」小节：明确 `目标学习语言`（entry 的 `lang` 字段）与 `界面语言`（entry 的 `interface_language` 字段）两个配置的来源与用途（kb item 用目标语言、vault 正文用界面语言）；同步更新设计文档 `docs/impl-spec/memory-writer-agent-spec.md` System prompt 小节
 - 2026-06-30 | Memory Writer Agent system prompt 注入 `src/everlingo/mem/agents/mem_entry_spec.md`：在 prefix 与 vault_spec 之间新增「输入 entry 结构」段，明确告知 LLM 其输入 JSON 的全部字段及含义（chat_session_id / entry_id / timestamp / channel_name / item_type / why_want_to_save_memory / user_intent / lang / interface_language / headword / mean_summary / conversation_context），机制与 Memory Extract Agent 加载 `mem_extract_output_spec.md` 一致；新增 `test_includes_entry_schema` / `test_entry_schema_appears_before_vault_spec` 两个回归测试；同步更新设计文档 `docs/impl-spec/memory-writer-agent-spec.md`「输入」与「System prompt」两节
 - 2026-06-30 | 修复 Memory Writer Agent system prompt 注入 spec markdown 的标题层级问题：`compile_prompt` 内部 `context_level` 机制只调整 include 子文件标题、不调整入口文件自身标题，导致注入的 `mem_entry_spec.md` / `vault_spec.md` 顶层 h1 比外层 `## 输入 entry 结构` / `## memory vault 结构` (h2) 还浅，结构断裂。新增 `src/everlingo/utils/md_prompt_compiler.py` 公开函数 `shift_headings(md, offset)`（基于 markdown-it AST 整体平移标题，钳制 1..6，不误判 fenced code block 内的 `#`，与 regex 版 `_demote_headings` 互补）；`_build_writer_system_prompt` 对两份 spec 文档各 `shift_headings(doc, 2)`，h1→h3 正确嵌套于 h2 父标题下。更新 `docs/impl-spec/markdown-prompt-compiler.md` 与 `docs/impl-spec/memory-writer-agent-spec.md` 记录约定。新增 `shift_headings` 单测 7 例 + writer system prompt 标题嵌套回归测试。Follow-up（未做）：`src/everlingo/agents/agent.py:47` 与 `src/everlingo/mem/agents/mem_extract_agent.py:41` 的 regex 版 `_demote_headings` 可改用 `shift_headings` 统一，消除重复实现并修复 fenced code 内 `#` 误判缺陷。

- 2026-06-29 | Memory Writer Agent 的 events 写入格式从「markdown 表格行」改为「markdown 段落」，对齐 `docs/impl-spec/worksplace/memory-vault-spec.md` 与 `events_spec.md:34-54` 的最新设计。`mem_writer_agent.py` 删除 `_EVENT_TABLE_HEADER`，新增 `_EVENT_FILE_PREAMBLE`（对应 `events_spec.md`「文件前置内容」）与 `_format_event_section`（返回 `## Event` + 字段列表 + `### mean_summary` + `### conversation_context` 一段，不再对 `|` 转义，`mean_summary` / `conversation_context` 保留原文换行）；`_append_event` 文件缺失时写 preamble、否则按 spec 段落追加；`mem_writer_tools` / `gateway` / kb item 写入路径未变。同步更新 `tests/test_mem_writer_agent.py`：`TestFormatEventRow` → `TestFormatEventSection`（断言字段名/值、`## Event`、`### mean_summary`、`### conversation_context`，验证多行 mean_summary 保留换行）、`TestAppendEvent` 断言 preamble 出现与两条 `## Event` 段、模块 docstring 同步更新；其他测试不需改。
- 2026-06-28 | Memory Extract Agent 改用独立 LLM 工厂 `create_extract_llm()`，temperature=0 以保证抽取任务的结构化输出确定性。改动：`src/everlingo/llm.py` 新增 `create_extract_llm()`（同 model/callbacks/tracing，仅 temperature=0）；`src/everlingo/mem/agents/mem_extract_agent.py` 切换 import 与调用；`docs/impl-spec/memory-extract-agent-spec.md` 同步更新「已知简化 / 待评估」段落标注已实施独立配置。`create_llm()` 保持 temperature=0.7 不变，主对话语气不受影响。
- 2026-06-28 | Memory Extract Agent 会话内 dedup 重构：废弃不稳定的 `session_seen_headwords` headword 字符串匹配（同一段历史被反复抽取且两次 headword 不一致），改为 `new_messages` / `context_messages` 输入侧硬隔离。`MainAgent` 持有 `_extract_cursor` 游标，每次 invoke 末尾切片：`new_messages = _messages[cursor:]`（唯一抽取来源）、`context_messages = _tail_recent_turns(_messages[:cursor], limit=19)`（仅供 `conversation_context`）。游标在 submit 前即推进，extract 失败也不再重抽本轮。`ExtractInput` 调整为 `new_messages` + `context_messages` 两字段；`MemoryExtractAgent` 自身完全无状态；system prompt 新增"抽取边界硬约束"。改动文件：`docs/impl-spec/memory-extract-agent-spec.md`、`src/everlingo/mem/agents/mem_entries.py`、`src/everlingo/mem/agents/mem_extract_agent.py`、`src/everlingo/agents/agent.py`、`tests/test_mem_extract_agent.py`。236 tests passed。
- 2026-06-28 | 实现 Memory Writer Agent 并接通 Extract Agent 写入流程。新增 `src/everlingo/mem/agents/mem_writer_tools.py`（9 个 mem_* 工具 + 内置 ULID 生成器，无新依赖；`_resolve_safe` 强制沙箱校验相对路径不逃出 memory_dir，防 `../` 与绝对路径）与 `src/everlingo/mem/agents/mem_writer_agent.py`（`MemoryWriterAgent` 全局单例，daemon thread + `queue.Queue`，与 Extract Agent 同构；system prompt 通过 `PackageSource` + `compile_prompt` 编译 `vault_spec.md`，自动展开 `{{ include kb_items_spec.md }}` / `{{ include events_spec.md }}`；events 写入用纯代码（按日期拼路径、表头自动创建、按 entry 追加行），kb item 写入通过 `create_agent(create_llm(), mem_*_tools, ...)` 逐 entry 调一次 LLM agent，让 LLM 自行 `grep → read → write`，每个目标文件至多一次 read / 一次 write；失败逐 entry 隔离、batch 级异常隔离；pragmatics 因 kb_items_spec 未定义专用模板，使用 system prompt 中的通用模板处理）。修改 `src/everlingo/gateway/gateway.py`：删除 `_StubMemoryWriter`，把 `memory_writer` 模块级单例改为延迟代理 `_MemoryWriterProxy`，首次 `enqueue` 时构造并 `start()` 真正的 Writer（避免 import 循环，行为对调用方不变）。Extract Agent 无改动（已通过 `gateway.memory_writer.enqueue` 转发）。新增 `tests/test_mem_writer_agent.py` 覆盖 ULID、沙箱、9 个工具、events 追加/创建、system prompt 内容、同步 `_process_batch` 与异步 daemon 路径、失败隔离、gateway 单例代理。244 tests passed。
- 2026-06-29 | Memory vault 写入语言规则在流水线落地：`MemoryEntry` 新增必需字段 `interface_language`（与 spec entry JSON 对齐，与 `lang` 对称、无默认值）；`_post_process` 从 Extract Agent 实例的 `self._interface_lang` 透传该字段，并在 `logger.info` 全字段输出中追加。Writer Agent 的 system prompt 在「# memory vault 注意事项」段内新增「## 写作语言」一节，指示 LLM 以 entry 的 `interface_language` 为 markdown 正文主要语言、`目标学习语言` 仅用于其词语/例句/示例/术语引用（接口与实现参考 `src/everlingo/mem/vault/vault_spec.md`「Markdown 文件使用什么语言编写」与 `docs/impl-spec/memory-writer-agent-spec.md` entry JSON）。`_render_entry_payload` 走 `model_dump()` 自动携带该字段，无需改动。改动文件：`src/everlingo/mem/agents/mem_entries.py`、`src/everlingo/mem/agents/mem_extract_agent.py`、`src/everlingo/mem/agents/mem_writer_agent.py`、`tests/test_mem_writer_agent.py`（`_entry()` fixture 同步补字段）、`TASKS.md`。Extract Agent system prompt / `LLMGeneratedEntry` / Extract 测试未改。

- 2026-06-28 19:35 | 日志格式重构：Formatter 升级为 `asctime.ms [level] [thread] [threadName] [module] [name] : msg`（millisecond 精度 + thread identity + module）；业务模块 logger 从共享 `"everlingo"` 改用 `__name__` 层级 logger（agents/agent、tracing、tools/__init__、tools/voice、gateway/gateway、mem/agents/mem_extract_agent、log_utils），子 logger 通过 propagate 上送根 handler；`docs/impl-spec/observability.md:7` 实现入口路径修正为 `log_utils.py`；`tests/test_log_utils.py` 新增 `test_setup_logging_format` 校验格式字段
- 2026-06-28 | Memory Extract Agent 可行性版本：实现 src/everlingo/mem/agents/mem_extract_agent.py（daemon thread + queue 异步消费、structured output、post-process 透传字段、session_seen_headwords 累积、USER.md 降级注入用于筛选判断、失败 logger.exception 丢弃不调 writer、本阶段精简筛选规则仅"用户明确要求记住"+"纠正事项"）+ src/everlingo/mem/agents/mem_entries.py（ExtractInput / MemoryEntry / ExtractLLMOutput / EntryWriterProtocol）；MainAgent 新增 session_id kwarg，__init__ 创建并 start 自己的 Extract Agent，invoke 返回前 submit ExtractInput（最近 20 轮 context_messages）；gateway.memory_writer 模块级单例（StubMemoryWriter 仅 info 日志记数量，Writer Agent 待实现）；tests/test_mem_extract_agent.py 30 例（覆盖透传字段、session_seen_headwords 累积、20 轮截取、submit 非阻塞、LLM 异常丢弃且后续继续、USER.md 空跳过、日志全字段输出、MainAgent 接线）
- 2026-06-27 11:42 | WechatChannel: SDK credentials 文件保存到 $workspace/plugins/channels/wechat_channel/credentials/credentials.json，init() 自动创建目录；新增 workspace.plugins_dir() 访问器
- 2026-06-27 17:40 | markdown prompt compiler：基于 markdown-it-py AST 实现 src/everlingo/utils/md_prompt_compiler.py，支持 `{{ include [label](path) }}` 独占段落指令、标题层级转换（子文件最浅标题→context_level+1，整体平移并钳制 1..6）、FilesystemSource 与 PackageSource、绝对路径强制 filesystem、循环检测与缺失文件报错；frontmatter 编译时剥离；输出为 markdown；新增 tests/test_md_prompt_compiler.py（20 例）

 - 2026-06-27 11:12 | 完成 workspace 概念实现：新增 `src/everlingo/workspace.py`（自包含路径解析，支持 CLI `--workspace` / `EVERLINGO_WORKSPACE` 环境变量 / 默认 `default` 三级优先级），重构 `setting.py` / `log_utils.py` / `tools/user_doc.py` / `models.py` / `main.py` 接入 workspace 模块，移除 `~/.everlingo` 硬编码路径。新增 `tests/test_workspace.py`（10 用例），更新 `tests/test_user_doc.py` / `test_unified_agent.py` / `test_setting.py` 切换到 workspace 模块。更新 `docs/impl-spec/worksplace/workspace.md` 补充选择机制与迁移说明。183 个测试全部通过。

 - 2026-06-23 10:00 | Channel Protocol: 新增 ChannelMetadata dataclass、send_sound 和 get_metadata 方法，以及对应测试
 - 2026-06-23 22:00 | 语音发送功能：新增 tts 模块（EdgeTTSProvider）、voice_speak 工具、Channel 改 ABC、Session 构造 MainAgent、分级语音 prompt 注入、动态 tool list、更新测试与文档
 - 2026-06-24 15:00 | 多消息回复：MainAgent.invoke 返回 list[MessageEvent]，每个非空 AIMessage.content 作为独立回复；Session 逐条 channel.send 形成多气泡；ToolMessage 不计入回复但保留在历史；更新测试与 chat-agent-spec.md / session.md
 - 2026-06-24 16:00 | 文档同步：按 README.md 重写 PRODUCT.md，明确区分"已经能做什么"和"正在路上"；补齐已实现的多端接入（微信/Web/TUI）与多语言支持描述；去除技术细节与图片
 - 2026-06-24 17:30 | Web 通道支持语音朗读：WebChannel.get_metadata 声明 mp3 支持（自动挂载 voice_speak 工具与分级 prompt），send_sound 广播 sound SSE 事件（base64 mp3），前端独立语音气泡含重听按钮（缓存 blob URL，无需后端再合成）；更新 tests/test_web_channel.py 与 docs/impl-spec/web-session-acceptor.md
 - 2026-06-24 18:00 | 修复 tests/test_web_acceptor.py 5 个失败用例：旧的 `_make_gateway` 用已废弃的 `Session(channel, agent=...)` 签名构造实例；改为用 MagicMock 模拟 session（测试只关心 web_acceptor 行为，不依赖 Session 内部实现）
 - 2026-06-24 19:00 | Web chatbot：等待服务端响应期间 textarea 不再禁用（用户可继续输入），同时在 handleSubmit 中加 pending 守卫阻止发送并保留已输入文本；发送按钮视觉逻辑保持不变（仅 disabled=disabled，pending 时 animate-pulse）

 - 2026-06-23 22:00 | SessionAcceptor.accept() 重命名为 start()，返回 asyncio.Task；WebSessionAcceptor.start() 非阻塞；Gateway.accept_session() 负责启动 session 协程并返回 task；Gateway.run() 简化为 await acceptor.start(self); await task
- 2026-06-22 14:30 | 撰写微信公众号推广文章：创建 /docs/ads/everlingo-intro.md，包含产品介绍、已实现特性（Chatbot对话、动态学习记忆、多端接入、多语言支持）、规划中特性（科学复习、浏览器插件、iPhone集成、学习档案）、技术架构简介、快速上手指南；文章面向技术开发者与外语学习者双重受众，约2500字，包含4处截图占位提示
- 2026-06-22 09:56 | 增加对法语(fr)、德语(de)的支持：更新 models.py(LANGUAGES字典、字段描述)、agent.py(system prompt)、everlingo.example.yaml(注释)、DOMAIN.md(语言列表)；添加对应测试用例
- 2026-06-22 10:15 | 修复发送按钮脉冲动画的竞态条件：将 setPending(true) 移到 await sendMessage() 之前，确保按钮状态正确还原
- 2026-06-22 11:30 | 新增 USER.md 用户自由偏好笔记机制：新建$workspace/memory/USER.md（Markdown 自由文本，动态注入 system prompt）；新增 user_doc toolset（user_doc_get/user_doc_set，写前备份 .bak）；从 UserProfile 移除 background/dictionary_definition_style（旧配置残留字段被 pydantic 静默忽略，不迁移）；prompt 版本号重构到 setting.py（bump_prompt_version/get_prompt_version），conf_manager 与 user_doc 共用；MainAgent 刷新逻辑改为版本号 + 文件 mtime 双检（外部编辑 everlingo.yaml/USER.md 也能即时刷新 system prompt）；更新 DOMAIN.md/configuration.md/tools.md/chat-agent-spec.md 及示例文件；新增 tests/test_user_doc.py 与 _build_system_prompt/重建相关测试
- 2026-06-22 12:15 | 修复 USER.md 标题注入层级冲突：新增 _demote_headings() 将 user_doc 内 markdown 标题在注入 system prompt 时降级两级（#→###, ##→####），避免与外围 "## 用户自由偏好笔记" 同级或更高级；更新 chat-agent-spec.md 说明；新增对应测试用例
- 2026-06-21 19:10 | 前端架构重构：引入 TailwindCSS v4 + shadcn/ui (New York)，拆分组件结构
- 2026-06-21 19:45 | 增大可视区域：ChatWindow 去掉 max-w-2xl 约束，改用 px-6 全宽布局
- 2026-06-21 19:45 | 调整发送按钮：增大按钮尺寸 (size="lg")，添加 SVG 向右箭头图标
- 2026-06-21 20:30 | 实现发送按钮脉冲动画提示：新增 pending 本地状态独立控制，发送后按钮 animate-pulse，收到回复后还原
- 2026-06-21 22:00 | 实现显式用户意图模式切换：/dict、/translate、/、/help 命令，SystemMessage 注入模式提示（不污染原文）
- 2026-06-21 10:30 | 实现 Web Session Acceptor 后端（WebChannel、WebSessionAcceptor/FastAPI、Gateway --channel_web）
- 2026-06-21 10:30 | 编写 WebChannel 和 WebAcceptor 单元/集成测试（17 个测试用例）
- 2026-06-21 10:30 | 初始化 Next.js 前端项目（Chatbot UI、SSE 集成、Markdown 渲染）
- 2026-06-21 11:00 | 替换为 Vite + React，简化前端结构（133 packages → 206，移除 App Router/use client/dynamic/etc）
- 2026-06-21 12:00 | Gateway 重构：Gateway 改为 class，支持多 Session 和 accept_session()；Session 新增 id/create_time/update_time/title 属性；创建 SessionAcceptor（Stdio/Wechat）；更新 main.py 和全部测试
 - 2026-06-18 | 编写 Wechat(微信) 消息 Channel。实现 `src/everlingo/gateway/channels/wechat_channel.py`（WechatChannel 类，使用 wechatbot-sdk，queue.Queue 线程安全消息队列）；更新 `gateway.py` 接入 WechatChannel，新增 `_run_wechat()` 函数；新增测试 `tests/test_wechat_channel.py`（8 个 Mock 测试，全部通过）。
 - 2026-06-18 | 使用 MIT 许可证。创建 `LICENSE` 文件，更新 `pyproject.toml` 添加 `license = "MIT"`
 - 2026-06-18 | 支持 `日本语(ja)` 作为 目标学习语言(target_language) 或 界面语言(interface_language)。更新 `models.py` LANGUAGES dict 和字段注释；更新 `agent.py` 重构 _lang_display_name() 引用 LANGUAGES 并更新 system prompt；更新 `everlingo.example.yaml` 和 `DOMAIN.md` 文档；添加日语相关测试用例。
 - 2026-06-18 | Agent 按需重建 system prompt（配置版本驱动）。思路：`conf_manager.py` 维护模块级 `_config_version` 计数器，`set_config` 工具每次成功写入后递增；`MainAgent.__init__()` 记录当时的版本号，每次 `invoke()` 前调用 `_refresh_agent_if_needed()`，发现版本号变化时用 `load_profile()` 重新构建 system prompt 并 `create_agent()`，版本号同步后不再重建。新增测试：`test_tools.py`（计数器递增/不递增 3 项）、`test_unified_agent.py`（no-rebuild / rebuild-once / rebuild-on-each-change 3 项），共 13 个单元测试全部通过。
 - 2026-06-20 | `Channel.recv()` 改为 async。Protocol 签名 `def recv` → `async def recv`；`StdioChannel.recv` 用 `asyncio.to_thread` 包装 `input()`；`WechatChannel.recv` 用 `asyncio.to_thread` 包装 `queue.Queue.get()`；`Session.run()` 中 `channel.recv()` 调用加 `await`；相关测试适配（AsyncMock / asyncio.run 包装），无新增依赖。
- 2026-06-17 23:58 | Agent 重构：Gateway / Session / Agent / Channel 抽象
  - **新增** `src/everlingo/gateway/channels/stdio_channel.py`：实现 `StdioChannel`，`recv` 阻塞读取 stdin，支持 `/quit` 退出和 EOF/KeyboardInterrupt；`send` 输出到 stdout。
  - **重构** `src/everlingo/agents/agent.py`：将 `_build_system_prompt` 和 Agent 构建逻辑从原 `chat.py` 迁入 `MainAgent`；修复 `invoke` 中 `messages` 变量名 bug（`self._messages` vs 局部变量）。
  - **实现** `src/everlingo/gateway/session.py`：`Session.run()` 完整消息循环——`channel.init()` → 循环 `channel.recv()` → `agent.invoke()` → `channel.send()`，收到 `None` 时退出。
  - **实现** `src/everlingo/gateway/gateway.py`：`argparse` 支持 `--channel_stdio` / `--channel_wechat`（wechat 暂未实现）；迁入 profile 初始化向导（`_ensure_profile`、`_run_profile_setup`）；`_run_stdio()` 组装并启动 Session。
  - **调整** `src/everlingo/main.py`：改为调用 `gateway._run_stdio()`，与 `gateway --channel_stdio` 等效。
  - **删除** `src/everlingo/chat.py`：原有逻辑已全部迁移至 gateway/agents 层。
  - **新增** `tests/test_gateway.py`：10 个单元测试覆盖 `StdioChannel`（recv 正常/quit/EOF/KeyboardInterrupt）和 `Session.run()`（消息循环、回复发回 channel）。
  - **修复** `tests/test_unified_agent.py`：将 `from everlingo.chat import _build_system_prompt` 改为 `from everlingo.agents.agent import _build_system_prompt`。
- 2026-06-17 23:58 | logging.py → log_utils.py（避免 shadow stdlib logging 导致 ImportError）；更新 main.py/llm.py/test_logging.py 的 import；launch.json wechat 配置改用 module 模式
- 2026-06-17 23:55 | 文件重命名：profile.py → setting.py（内容已不限于 UserProfile），同步更新所有 import 引用，PROFILE_PATH → SETTING_PATH，test_profile.py → test_setting.py
- 2026-06-17 23:50 | UserProfile 结构对齐 everlingo.example.yaml：新增 UserLanguage/UserBackground 子模型，interface_language/target_language 移入 language 下，hobbies/residence/gender 移入 background 下；更新 setting.py（简化为 model_validate/model_dump）、chat.py、test_setting.py、test_unified_agent.py
- 2026-06-17 23:30 | 配置实现由 dataclass 重构成 pydantic
- 2026-06-17 23:00 | 实现 LLM tool 调用日志：添加 log_tool_call 装饰器并应用到所有 tool 函数，日志格式为 tool_name + parameters + return，debug 级别
- 2026-06-16 19:45 | 修复 Langfuse 4.x 兼容性：CallbackHandler 不再接受凭证参数，改为先初始化 langfuse.Langfuse(secret_key/public_key/host) 配置 OTEL exporter，再创建无参 CallbackHandler()
- 2026-06-16 19:30 | 配置文件结构修正：logging_setting/tracing_setting 移入 sys_setting 下，修正 models.py、profile.py、everlingo.example.yaml、tracing.py、logging.py 及相关测试文件
- 2026-06-16 18:00 | 添加 __main__.py 使 python -m everlingo 可用，支持 VSCode debug 的模块模式
- 2026-06-16 18:00 | 创建 .vscode/launch.json debug 配置（module 模式 + PYTHONPATH）
- 2026-06-16 15:20 | 实现 Tracing 配置：TracingSetting dataclass 及序列化/反序列化、更新 everlingo.example.yaml 示例配置
- 2026-06-16 15:20 | 实现 Langfuse 跟踪 LLM 流量：setup_tracing() 集成 Langfuse CallbackHandler 到 LLM
- 2026-06-16 10:30 | 实现多轮会话支持：chat.py 累积 messages 历史，agent.invoke 传入完整历史上下文而非单条消息
- 2026-06-16 10:30 | 实现 Observability 日志系统：LLM 请求/响应写入 $workspace/logs/everlingo.log，日志级别 debug
- 2026-06-16 10:30 | 实现 LoggingSetting 配置项：log_file / log_level 可配置，集成到 EverLingoSetting 序列化
- 2026-06-15 17:33 | 重构为统一 Agent 架构：移除 IntentAnalyzer，使用单一 LangChain Agent 处理所有意图（查词、翻译、配置管理）
- 2026-06-15 10:30 | 重构 tools 为多 toolset 架构


- 修改为基于 langchain agent 的 LLM 交互 (`from langchain.agents import create_agent`):
  - 新建 `tools.py`：实现 configuration_manager tool（get_schema/get_config/set_config）
  - 修改 `llm.py`：添加 create_agent() 工厂函数，包装 langchain.agents.create_agent
  - 修改 `dict_teacher.py`：接受 agent 替代 ChatOpenAI，使用 agent.invoke({"messages": [...]})
  - 修改 `trans_teacher.py`：同上模式
  - 修改 `chat.py`：为每位老师创建独立的 agent，system_prompt 在创建时注入
  - 更新对应测试：mock agent 返回 {"messages": [AIMessage(...)]}

- 建立一个 langchain python 开发环境的 code base
- 项目结构: `pyproject.toml`, `src/everlingo/`, `tests/`
- Domain models: `UserProfile`, `WordQuery`, `TranslationRecord`
- LLM 集成: LangChain + ChatOpenAI (兼容 OpenAI Chat Completions endpoint)
- 用户个性初始化: 界面语言 + 目标学习语言 (英语/简体中文)
- 意图分析: 规则驱动 (查单词 / 翻译)
- 词典老师: LLM 驱动的单词解释 (释义、词源、文化背景)
- 翻译老师: LLM 驱动的翻译 (含句式分析)
- TUI Chatbot: 终端 REPL 聊天循环
- 按照 impl-spec/configuration.md 生成 /.env.example 和 /everlingo.example.yaml
- 按照 impl-spec/configuration.md 修改配置代码:
  - config.py: 支持从 YAML sys_setting 读取配置，优先级高于环境变量
  - profile.py: 改用 YAML 格式，位置 `$workspace/everlingo.yaml`，支持嵌套 user_profile 结构
  - models.py: UserProfile 增加 background 和 dictionary_definition_style 字段
  - pyproject.toml: 添加 pyyaml 依赖
- 配置文件结构修正: 顶层配置对象改为 `EverLingoSetting`，包含 `SysSetting` 和 `UserProfile`
  - models.py: 新增 `SysSetting`、`EverLingoSetting` 类
  - profile.py: 新增 `load_setting()`/`save_setting()`，以 `EverLingoSetting` 为顶层对象
  - config.py: 改用 `load_setting().sys_setting` 获取系统配置
