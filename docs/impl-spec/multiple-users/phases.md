# 多用户支持 — 分阶段实现计划

- 状态：Planned（2026-07-29）
- 相关文档：
  - [ws-router.md](./ws-router.md)
  - [ws-master.md](./ws-master.md)
  - [internal-api-contract.md](./internal-api-contract.md)
  - [deploy.md](./deploy.md)
  - [external-nginx.md](./external-nginx.md)
- 定位：本文件是 `docs/impl-spec/multiple-users/` 下多用户支持的**实现路线与跟踪表**。
  每个 PR 的目标、范围、依赖、测试策略、验收点在此固定，便于按序推进与状态跟踪。
  业务设计见上述相关文档，本文件只管「怎么分步实现」。

---

## 总览

| PR | 标题 | 依赖 | 状态 |
|---|---|---|---|
| PR0 | 依赖与骨架 | — | ✅ |
| PR1 | WS-Master 模块 | PR0 | ⬜ |
| PR2 | WS-Router 模块 | PR0 + PR1 契约 | ⬜ |
| PR3 | 部署编排 | PR1 + PR2 | ⬜ |
| PR4 | Chrome Extension Token 化 | PR2 | ⬜ |

状态标记：⬜ Planned / 🚧 In Progress / ✅ Done / ⚠️ Blocked。

依赖关系图：

```
PR0 ──▶ PR1 ──▶ PR3
        │  ▲
        ▼  │
        PR2 ──▶ PR4
```

- PR2 依赖 PR1 的 **Internal API 契约**（[internal-api-contract.md](./internal-api-contract.md)），
  不依赖 PR1 的实现；契约已落盘，故 PR1 与 PR2 可并行开发，但 PR2 集成测试需 PR1 实现就位。
- PR3 依赖 PR1 + PR2 源码就位（镜像构建需要两个包存在）。
- PR4 依赖 PR2 的 `/login` JSON 接口与 PAT 机制定型。

---

## PR0 — 依赖与骨架

**目标**：为后续 PR 提供依赖与空包骨架，不实现任何业务逻辑。

### 范围

- `pyproject.toml` 新增依赖（**需审批**，AGENTS.md 规定不得擅自加依赖）：
  - `docker>=7.0`（WS-Master 容器生命周期编排）
  - `pyjwt>=2.8`（WS-Router JWT 签发/验签）
- 新建空包骨架：
  - `src/everlingo/ws_router/`（`__init__.py` + `__main__.py` 占位）
  - `src/everlingo/ws_master/`（`__init__.py` + `__main__.py` 占位）
- `src/everlingo/main.py` / `__main__.py` 增加 `ws_router` / `ws_master` 子命令派发
  （仅 `--help` 可用程度，不启动任何服务）
- `uv sync` 验证依赖安装无冲突

### 测试

- 单测：子命令派发不爆栈（`everlingo ws_router --help` / `everlingo ws_master --help` 退出码 0）

### 验收点

- `uv sync` 成功
- `everlingo ws_router --help` 与 `everlingo ws_master --help` 可执行
- 两个空包目录存在且可 import

### 阻塞风险

- 依赖审批卡点：若 `docker` / `pyjwt` 未批准，PR1/PR2 无法开工。建议 PR0 提交时附依赖用途说明。

---

## PR1 — WS-Master 模块

**目标**：实现后台编排服务（[ws-master.md](./ws-master.md)），按 [internal-api-contract.md](./internal-api-contract.md) 实现 Internal API。

### 范围（按内部依赖顺序分三层 commit）

#### 1.1 数据层

- `ws_master.sqlite` schema：
  - `users`（含 `openai_*` 四 nullable 字段，Phase 1 恒 NULL）
  - `user_identities`（Phase 1 建表不写入）
  - `pat_tokens`
  - `ws_containers`
- schema 迁移逻辑（首次创建 + 幂等）
- 数据访问层（纯 sqlite CRUD，无业务逻辑）

#### 1.2 CLI 层

- `everlingo ws_master <subcommand>`，直连 sqlite，不走 daemon：
  - `user add/list/rm`
  - `pat add/list/rm`
  - `ws add/list/rm/start/stop/set-default`
  - `identity list/unlink`
- `user add` 同步创建 default ws-container（status=absent）

#### 1.3 Internal API + 容器生命周期

- FastAPI app 监听 8101，`X-Master-Token` 校验中间件
- 端点实现（契约见 [internal-api-contract.md](./internal-api-contract.md)）：
  - `POST /internal/authenticate`
  - `POST /internal/pat/verify` + `POST /internal/pat`
  - `GET /internal/users/{user_id}` + `GET /internal/users/{user_id}/ws`
  - `GET /internal/users/{user_id}/default-ws/backend`
  - `GET /internal/ws/{ws_container_id}/backend` + `POST /internal/ws/{ws_container_id}/ensure_started`
  - `GET /internal/healthz`
- docker SDK 容器生命周期：
  - create / start / stop / remove
  - 探活（httpx 轮询 backend health）
  - lazy start 状态机（[ws-master.md](./ws-master.md) §6.1 + §7）
  - 并发控制（per-ws `asyncio.Lock` + in-flight 结果复用）
  - idle timeout 后台 task（`healthcheck_interval` 周期探活 + SSE client 计数判 idle）
  - WS-Master 启动对账（遍历 DB 中 creating/starting/started 行回写 docker 实际状态）
- `ws_container_everlingo_template.yaml` 拷贝初始化逻辑

### 测试

- **数据层**：纯 sqlite 单测（schema 创建、CRUD、约束如 `UNIQUE(provider,subject)`、`user_name` 唯一）
- **CLI 层**：单测覆盖各子命令（用临时 sqlite 文件）
- **Internal API**：`httpx.AsyncClient` + mock docker SDK：
  - 各端点的成功 + 错误码（覆盖契约 §2 每个端点的错误表）
  - 状态机流转：absent→creating→starting→started、stopped→starting→started、error 路径
  - 并发：同一 ws 多个并发 backend 请求复用 in-flight 结果
  - lazy start 超时 → 503
- **容器生命周期**：默认 skip 的集成测试（需真 docker daemon，标 `@pytest.mark.integration`）

### 验收点

- `everlingo ws_master user add --name mark --display-name "Mark"` 成功，sqlite 有记录
- `everlingo ws_master pat add --user mark --label "curl-laptop"` 打印明文 token
- curl 带 `X-Master-Token` 调 `/internal/users/{uid}/default-ws/backend`（mock docker）返回 `backend_url`
- 所有 Internal API 单测通过，覆盖契约中每个错误码

---

## PR2 — WS-Router 模块

**目标**：实现前台反代 + 认证服务（[ws-router.md](./ws-router.md)），消费 [internal-api-contract.md](./internal-api-contract.md)。

### 范围

#### 2.1 AuthProvider + PasswordAuthProvider

- `AuthProvider` Protocol（[ws-router.md](./ws-router.md) §3.4）
- `PasswordAuthProvider`：`POST /login`（表单 + JSON 双格式）、委派 WS-Master `/internal/authenticate`
- JWT 签发/验签（HS256，载荷 `{sub: user_id, user_name, exp, jti}`，TTL 8h）
- `GET /me`（调 WS-Master `/internal/users/{uid}` 取 display_name，带缓存）
- `GET /logout`、登录页 HTML（服务端渲染，[ws-router.md](./ws-router.md) §4.3）

#### 2.2 auth_middleware

- `Authorization: Bearer` → JWT 本地验签 → 失败回退 PAT 委派 WS-Master `/internal/pat/verify`（LRU 缓存 TTL=30s）
- 无 Bearer → cookie `everlingo_sess` → JWT 验签
- 均无且非白名单路径 → 浏览器 302 `/login` / 程序化 401 JSON（按 `Accept` 分流）

#### 2.3 backend_resolve + 反代

- `GET WS-Master /internal/users/{uid}/default-ws/backend`（LRU 缓存 TTL=60s，key=user_id）
- `httpx.AsyncClient` 反代，SSE 端点用 `client.stream`
- 剔除 `Cookie` / `Authorization` / hop-by-hop 头，注入 `X-Everlingo-User: <user_id>`
- 503 `backend_unavailable` 处理（`details.status` 区分 starting/error 决策重试或错误页）

#### 2.4 trusted_proxy + CORS

- `trusted_proxy` 中间件：按 `X-Forwarded-Proto` 设 cookie Secure 位（仅信任配置的来源 IP）
- CORSMiddleware：`cors_allow_origins` 白名单（chrome-extension origin），`allow_credentials=False`

### 测试

- **JWT**：签发/验签/过期/篡改 单测
- **auth_middleware**：mock WS-Master client，覆盖 JWT / PAT / cookie / 未认证四条路径 + 浏览器/程序化分流
- **反代**：`httpx.MockTransport` 模拟后端 ws-container，覆盖普通请求 + SSE 流式透传 + hop-by-hop 头剔除
- **CORS**：OPTIONS 预检单测
- **登录页**：`GET /login` 返回 HTML、`POST /login` 表单/JSON 双格式

### 验收点

- mock 掉 WS-Master 后：login（JSON）→ 拿 access_token → 带 Bearer 访问 `/api/session/...` → 透传到 mock 后端
- 同流程用 cookie 版本（浏览器 `Accept: text/html`）→ 302 `/`
- SSE 端点流式透传正常

### 依赖点

- 依赖 PR1 的 Internal API 契约（已落盘），不依赖 PR1 实现
- 集成测试（连真 WS-Master）需 PR1 就位

---

## PR3 — 部署编排

**目标**：让整套拓扑能在真机器上跑起来。依赖 PR1 + PR2 源码就位。

### 范围

- 镜像构建：
  - `docs/impl-spec/deploy/image/Dockerfile.ws_router`（精简构建，跳过 frontend-builder，无 `web/dist`）
  - `docs/impl-spec/deploy/image/Dockerfile.ws_master`（同上精简构建）
- `docker-compose.yml`（[deploy.md](./deploy.md) §2）：
  - `ws_router` + `ws_master` + `everlingo-net` + `master-data` volume
  - `DOCKER_GID` / `HOST_WS_DIR` 环境注入
- 示例配置文件：
  - `ws_router.yaml` 示例
  - `ws_master.yaml` 示例
  - `ws_container_everlingo_template.yaml` 挂载
- 外部 nginx 配置示例落地（[external-nginx.md](./external-nginx.md) §3）
- 部署步骤文档化（[deploy.md](./deploy.md) §6）

### 测试

- 基本手工/半自动验证，无单测
- CI 可加 `docker compose config` 语法校验

### 验收点

- 在一台带 docker 的机器上，按 [deploy.md](./deploy.md) §6 步骤：
  1. 构建两个镜像
  2. `docker compose up -d`
  3. `ws_master user add` + `pat add`
  4. 配置 nginx + reload
  5. 浏览器访问 → 登录 → 主 SPA（由 ws-container 提供）→ 正常使用
- ws-container 由 WS-Master 动态创建，`docker ps` 可见 `everlingo-<user>-<short_id>`

---

## PR4 — Chrome Extension Token 化

**目标**：替换现有 Basic Auth，改用 PAT/access_token。多用户上线后的客户端适配。

### 范围

- Extension Options 加 Token 配置字段（PAT 或 access_token）
- 或弹窗内「登录」按钮调 WS-Router `POST /login`（JSON）拿 access_token 存 `chrome.storage`
- 请求 WS-Router 时带 `Authorization: Bearer <token>`
- 涉及 `extension/` 下 envelope.ts / 请求层改造

### 测试

- extension 端 ts 测试覆盖 token 注入
- 可加 mock WS-Router 的集成测试

### 验收点

- Extension 配置 PAT 后，请求自动带 Bearer，WS-Router 认证通过
- 或弹窗登录 → access_token 存储 → 后续请求自动带

### 依赖点

- 依赖 PR2 的 `/login` JSON 接口与 PAT 机制定型

---

## 横切关注点

### 依赖审批

`docker>=7.0` 与 `pyjwt>=2.8` 是新依赖（AGENTS.md 规定不得擅自加）。PR0 卡在审批上，
建议 PR0 提交时附用途说明：
- `docker`：WS-Master 通过 docker SDK 管理 ws-container 生命周期（create/start/stop/remove）
- `pyjwt`：WS-Router JWT 签发/验签（HS256，本地无状态校验）

### 集成测试边界

- 默认 skip 真 docker daemon 测试（标 `@pytest.mark.integration`）
- CI 仅跑 mock 版本
- 本机 `pytest -m integration` 跑真 docker 集成

### Phase 1 收敛

Phase 1 严格收敛到（设计文档已明确）：
- 单 ws/user（`max_ws_per_user: 1`）
- 仅 `password` provider（`AuthProvider` 只实现 `PasswordAuthProvider`）
- 全局 LLM key（`users.openai_*` 恒 NULL，回退 `ws_master.yaml`）
- `user_identities` 表建表不写入
- 多 ws / SSO / per-user key 均为 Phase 2+，Phase 1 只保留 schema 与抽象

### Internal API 契约稳定性

- [internal-api-contract.md](./internal-api-contract.md) 是 PR1/PR2 共同边界
- 契约变更须双方向该文件提 PR 同步，不得单边改实现
- 新增可选字段为兼容变更；破坏性变更（删端点/改字段语义）需双方协调

---

## 已确认的关键决策

| # | 决策 | 确认于 |
|---|---|---|
| D1 | Internal API 契约独立文件 `internal-api-contract.md` | 2026-07-29 |
| D2 | 错误响应用结构化 `{error:{code,message,details}}` | 2026-07-29 |
| D3 | `authenticate`/`pat/verify` 成功响应一并返回 `{user_id,user_name,display_name}` + 独立 `GET /internal/users/{uid}` | 2026-07-29 |
| D4 | JWT 载荷额外放 `user_name`（不可改），`display_name` 走 `/me` 查询 | 2026-07-29 |
| D5 | `POST /internal/pat` Phase 1 实现但 ws-router 不调用 | 2026-07-29 |
| D6 | `authenticate` 对不存在用户统一 401 防枚举 | 2026-07-29 |
| D7 | `default-ws/backend` 正在 starting 时阻塞最多 `readiness_timeout` 秒再 503 | 2026-07-29 |
| D8 | 并发同一 ws 复用 in-flight 结果短暂等待，超时 503 | 2026-07-29 |
| D9 | PAT 明文格式 `elpat_<base62>` | 2026-07-29 |
| D10 | `users/{id}/ws` 响应含 `container_name` 字段 | 2026-07-29 |
| D11 | `/internal/healthz` 成功响应 `{"status":"ok"}` | 2026-07-29 |

---

## 变更记录

- 2026-07-29 | 初版：PR0~PR4 分阶段计划，含 Internal API 契约决策（D1~D11）。
