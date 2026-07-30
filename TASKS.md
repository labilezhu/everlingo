# Tasks

## 计划的任务

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"

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
