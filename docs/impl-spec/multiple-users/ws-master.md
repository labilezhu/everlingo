# WS-Master Service

- 状态：Planned（2026-07-29 修订）
- 进程入口：`python -m everlingo ws_master --config ws_master.yaml`（见 [app-entry.md](../app-entry.md)）
- 相关文档：
  - [ws-router.md](./ws-router.md)
  - [deploy.md](./deploy.md)
  - [external-nginx.md](./external-nginx.md)
  - [container-spec.md](../deploy/image/container-spec.md)（workspace container 镜像规范）

---

## 1. 职责

WS-Master 是多用户部署拓扑中的**后台编排服务**，运行于独立容器（见 [deploy.md](./deploy.md)）。它仅在 `everlingo-net` 内可达，不对公网暴露。负责：

- **数据所有者**：维护 `ws_master.sqlite` 的 `users` / `user_identities` / `pat_tokens` / `ws_containers` 四张表
- **认证校验后端**：校验用户名口令、校验 PAT、SSO 身份映射
- **workspace container 生命周期**：create / start / stop / remove ws-container（lazy 启动 + idle 停机）
- **服务发现**：向 WS-Router 提供 `user_id → backend_url` 解析（经 default ws-container）
- **CLI 运维**：用户增删、PAT 管理、ws-container 查询与操作

WS-Master **不**反代用户流量、**不**面向公网、**不**签发 WS-Router 的 JWT（JWT 由 WS-Router 用共享 `jwt_secret` 本地签发与验签）。

## 2. 概念模型：workspace container（ws-container）

**workspace container**（简称 ws-container）即 [container-spec.md](../deploy/image/container-spec.md) 描述的容器实例——一个运行 everlingo 双进程（indexer + gateway）的 docker container，承载一个 workspace 的全部数据与进程。

引入此概念是为了把「容器生命周期」与「用户身份」解耦：

- 每个 ws-container 对应一个独立的 workspace（独立 sqlite / memory vault / logs）。
- 一个 user 架构上可拥有**多个** ws-container（多 workspace）。
- Phase 1 限制每 user 最多 1 个 ws-container（`max_ws_per_user: 1`）；数据模型与 API 已按多 ws 形状设计，未来放开限制无需 breaking change。

### 2.1 ws-container 属性

| 属性 | 说明 |
|---|---|
| `ws_container_id` | UUID，主键 |
| `host_workspace_dir` | 宿主侧绝对路径 `<host_ws_dir>/<user_name>/<ws_container_id>/` |
| `state` | 生命周期状态，见 §4 |
| `docker_container_id` | docker create 后回填的容器 ID |
| `docker_container_name` | `everlingo-<user_name>-<short_id>`，`short_id` = `ws_container_id` 前 8 位 |
| `is_default` | 是否为该 user 的默认 ws-container（路由用）；每 user 恰好一个 default |

### 2.2 命名约定

- docker container name / network alias：`everlingo-<user_name>-<short_id>`
  - 例：`everlingo-mark-a1b2c3d4`
  - `short_id` = `ws_container_id` UUID 前 8 位，保证跨 ws-container 唯一且可读
- 宿主 workspace 目录：`<host_ws_dir>/<user_name>/<ws_container_id>/`
  - 用 `user_name`（不可修改）而非 `user_id`，便于运维排查
  - 目录结构示例：
    ```
    <host_ws_dir>/
      mark/
        <ws_container_id_1>/
        <ws_container_id_2>/
      alice/
        <ws_container_id_3>/
    ```

## 3. 拓扑位置

```
WS-Router ──http──▶ WS-Master(:8101, everlingo-net only)
                       │
                       │ docker SDK (unix:///var/run/docker.sock, 挂载)
                       ▼
                   Docker daemon
                       │
                       │ create/start/stop (network=everlingo-net, alias=everlingo-<user>-<short_id>)
                       ▼
                   everlingo-<user>-<short_id>:8000  (仅 everlingo-net 内可达)
```

WS-Master 容器挂载宿主 `/var/run/docker.sock`，通过 `group_add` 注入宿主 docker GID 获得访问权限（见 [deploy.md](./deploy.md) §权限）。

## 4. 数据模型

数据库文件：`~/.everlingo/ws_master.sqlite`（WS-Master 容器内挂载持久化 volume）。

### 4.1 `users`

| 字段 | 类型 | 说明 |
|---|---|---|
| `user_id` | TEXT PK | UUID |
| `user_name` | TEXT UNIQUE | 英文字母+下划线，用作容器名与 workspace 目录名。**不可修改** |
| `user_display_name` | TEXT | 展示名 |
| `password_hash` | TEXT | bcrypt 哈希；本地口令认证凭证（`PasswordAuthProvider` 查此字段） |
| `created_at` | TEXT | ISO8601 |
| `openai_api_key` | TEXT NULL | 远期 per-user key 预留；Phase 1 恒为 NULL，回退 `ws_master.yaml` |
| `openai_base_url` | TEXT NULL | 同上 |
| `openai_model` | TEXT NULL | 同上 |
| `openai_embedding_model` | TEXT NULL | 同上 |

> 变更说明：原 `workspace_dir` 字段移除——workspace 现属 ws-container 级别，由 `ws_containers.host_workspace_dir` 表达。原 `sso_subject` 字段移除——外部 IdP 身份信息移至独立 `user_identities` 表（§4.2），支持多 SSO provider 并存与一个 user 绑定多 provider。`openai_*` 四字段为远期 per-user key 预留（见  per-user key roadmap），Phase 1 全部 NULL，由 `ws_master.yaml` 全局配置 + `ws_container_everlingo_template.yaml` 模板兜底。

### 4.2 `user_identities`

外部 IdP（Identity Provider）身份映射表。一个 user 可绑定**多个** provider（既 Google 又 GitHub）；一个 `(provider, subject)` 只能映射到唯一 user。

> 设计动机：本地认证（user_name + password_hash）与外部 SSO 身份是不同性质——password 是可改的凭证，`(provider, subject)` 是外部 IdP 已验证的稳定身份。两者职责分离：`PasswordAuthProvider` 查 `users` 表，`GoogleSSOAuthProvider` 等 SSO provider 查 `user_identities` 表，各走各的。`AuthProvider` 抽象在 WS-Router 侧统一两类登录入口，但底层数据存储不强行合并。

| 字段 | 类型 | 说明 |
|---|---|---|
| `identity_id` | TEXT PK | UUID |
| `user_id` | TEXT FK→users | 一个 user 可有多条 |
| `provider` | TEXT | IdP 标识：`google` / `github` / ...（与 `ws_router.auth.providers` 对应） |
| `subject` | TEXT | provider 侧唯一 ID（Google `sub`、GitHub `node_id` 等） |
| `email` | TEXT NULL | provider 上报的 email（信息性，不强制唯一——可能未验证/跨 provider 不同/会变） |
| `display_name` | TEXT NULL | provider 上报的展示名（自动建用户时用于生成 `user_display_name`） |
| `created_at` | TEXT | |
| `last_used_at` | TEXT NULL | SSO 登录命中时回写 |

**约束**：
- `UNIQUE (provider, subject)` — 同一 provider+subject 只能映射到一个 user（防一身份绑两账户）。
- `user_id` 不唯一 — 一个 user 可绑多个 provider（多 SSO 并存）。
- 索引：`(provider, subject)` 为主查询路径（SSO 回调命中）；`(user_id)` 用于列「我的绑定」。

**Phase 1**：表结构与约束随 schema 建立，但仅 `PasswordAuthProvider` 启用，无 SSO 数据写入。Phase 2+ 启用 SSO provider 时直接写入此表。

### 4.3 `pat_tokens`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | TEXT PK | UUID |
| `user_id` | TEXT FK→users | |
| `token_hash` | TEXT | sha256(明文) |
| `label` | TEXT | 人类可读标签，如 `curl-laptop` |
| `created_at` | TEXT | |
| `last_used_at` | TEXT NULL | WS-Router 校验时回写 |
| `expires_at` | TEXT NULL | NULL = 永久 |

明文 token 生成时返回一次，不存储。

### 4.4 `ws_containers`

> 取代原 `containers` 表（原表以 `user_id` 为 PK，排斥多 ws）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `ws_container_id` | TEXT PK | UUID |
| `user_id` | TEXT FK→users | |
| `container_name` | TEXT UNIQUE | `everlingo-<user_name>-<short_id>` |
| `docker_container_id` | TEXT NULL | docker create 后回填 |
| `status` | TEXT | 见 §5 状态机 |
| `host_workspace_dir` | TEXT | 宿主绝对路径 |
| `is_default` | INTEGER | 0/1，每 user 恰好一个 1 |
| `created_at` | TEXT | ISO8601 |
| `started_at` | TEXT NULL | 最近一次进入 started 的时间 |
| `last_seen_at` | TEXT NULL | 最近一次探活成功时间 |
| `error_message` | TEXT NULL | status=error 时填写原因 |

**约束**：
- `container_name` UNIQUE（docker 容器名全局唯一）。
- 每 user 恰一个 `is_default=1`（应用层强制；`user add` 时同步创建的 ws-container 即为 default）。
- Phase 1 通过应用层强制每 user 最多 1 行（`ws add` 时若已存在则拒绝），DB 不加 UNIQUE 约束以便未来放开 `max_ws_per_user`。

## 5. 配置

### 5.1 `ws_master.yaml`

> 原 `everlingo_master.yaml` 重命名。`workspace_workspaces` 字段重命名为 `host_ws_dir`（语义更清晰）。LLM 配置保留于此，作为容器 env 注入源与 per-user key 的 fallback。

```yaml
master:
  listen: 127.0.0.1:8101           # everlingo-net 内监听；容器内即 0.0.0.0:8101
  shared_secret: <random>          # X-Master-Token（与 ws_router.master_secret 一致）
  db: /root/.everlingo/ws_master.sqlite
  host_ws_dir: /workspaces         # 宿主侧 workspace 根（容器内挂载点）

  image: ghcr.io/labilezhu/everlingo:0.0.1-rc.3
  network: everlingo-net
  ws_template: /etc/everlingo/ws_container_everlingo_template.yaml  # 新建 ws-container 的 everlingo.yaml 模板

  # LLM 配置：作为容器 env 注入 ws-container；远期 per-user key 启用时优先读 users.openai_*
  openai_api_key: ${OPENAI_API_KEY}
  openai_base_url: https://openrouter.ai/api/v1
  openai_model: deepseek/deepseek-v4-flash
  openai_embedding_model: baai/bge-m3

  idle_timeout: 1200                # 无 SSE client 持续秒数 → stop（默认 20 分钟）
  healthcheck_interval: 60          # 探活间隔秒数
  readiness_timeout: 60             # create/start 后等待 backend 就绪秒数
  max_ws_per_user: 1                # Phase 1 = 1；未来放开以支持多 ws
```

**LLM 密钥流向**：
- `ws_master.yaml` 的 `openai_*` 由 WS-Master 读取（自身 env 展开 `${VAR}`），作为**容器 env** 注入 ws-container。
- **不**写入 workspace 的 `everlingo.yaml`——密钥不落宿主磁盘（workspace 目录在宿主上可被运维访问）。
- ws-container 内 `config.py:get_llm_config()` 的 env fallback（`ss.openai_api_key or os.getenv("OPENAI_API_KEY")`）自动生效。
- 远期 per-user key：优先读 `users.openai_*`，为空则回退 `ws_master.yaml`。

### 5.2 `ws_container_everlingo_template.yaml`

新建 ws-container 时，WS-Master 将此模板拷贝到 `<host_workspace_dir>/everlingo.yaml`，作为该 workspace 的初始配置。模板内容见 [ws_container_everlingo_template.yaml](./ws_container_everlingo_template.yaml)。

关键约定：
- `sys_setting.openai_*` **留空**——依赖容器 env fallback（`config.py` 已支持），避免密钥落盘。
- `user_profile.language` 仅放**默认值**——用户首次进入后可在 UI 修改并写回此文件（复用现有 `save_profile` 逻辑）。
- `plugins.channels.channel_web.public_address.base_url` 留空——ws-container 经 ws-router 反代，无需感知外部域名。

## 6. Internal API

WS-Master 监听 `everlingo-net` 内 `ws_master:8101`，所有请求校验头 `X-Master-Token: <shared_secret>`。未带或不符 → 401。

| Method | Path | 用途 |
|---|---|---|
| POST | `/internal/authenticate` | 入参 `{username, password}` → `{user_id}` 或 401 |
| GET | `/internal/users/{user_id}/ws` | 列出该 user 的 ws-container：`[{ws_container_id, status, is_default}]` |
| GET | `/internal/users/{user_id}/default-ws/backend` | 解析 default ws-container → lazy start + 返回 `{ws_container_id, backend_url, status}` |
| GET | `/internal/ws/{ws_container_id}/backend` | 按 ws-container id lazy start + 返回 `{backend_url, status}` |
| POST | `/internal/ws/{ws_container_id}/ensure_started` | 强制拉起（即使 status=started 也探活） |
| POST | `/internal/pat/verify` | 入参 `{token}` → `{user_id}` 或 401；成功时回写 `last_used_at` |
| POST | `/internal/pat` | 入参 `{user_id, label, expires_at?}` → `{token, id}`（明文仅返回一次） |
| GET | `/internal/healthz` | 自检 |

> API 按多 ws 形状设计（`/ws`、`/ws/{id}/backend`），Phase 1 WS-Router 实际调用便捷端点 `default-ws/backend`。未来放开多 ws 时，WS-Router 可改为先列 ws 让用户选择，再调 `/internal/ws/{id}/backend`，无需 breaking change。原 `GET /internal/users/{user_id}/backend` 删除（语义含糊，被 default-ws/backend 取代）。

### 6.1 `GET /internal/users/{user_id}/default-ws/backend` 行为

1. 查 `ws_containers` 表中 `user_id` 且 `is_default=1` 的行
2. `status=started` 且探活成功 → 返回 `http://everlingo-<user_name>-<short_id>:8000`
3. `status=stopped` → `docker start` → 探活就绪 → 返回 URL
4. `status=absent` → `docker create`（挂载 host_workspace_dir、注入 env、network=`everlingo-net`、alias=`everlingo-<user_name>-<short_id>`、不设 ports）→ `docker start` → 探活就绪 → 返回 URL
5. 探活失败超 `readiness_timeout` → 返回 503

### 6.2 创建 ws-container 参数

```python
short_id = ws_container.ws_container_id[:8]
container_name = f"everlingo-{user.user_name}-{short_id}"

docker.containers.create(
    image=master_config.image,
    name=container_name,
    network=master_config.network,
    network_aliases=[container_name],
    environment={
        "OPENAI_API_KEY": user.openai_api_key or master_config.openai_api_key,
        "OPENAI_BASE_URL": user.openai_base_url or master_config.openai_base_url,
        "OPENAI_MODEL": user.openai_model or master_config.openai_model,
        "OPENAI_EMBEDDING_MODEL": user.openai_embedding_model or master_config.openai_embedding_model,
        "EVERLINGO_WORKSPACE_DIR": "/home/everlingo/.everlingo/workspaces/default",
    },
    volumes={
        ws_container.host_workspace_dir: {
            "bind": "/home/everlingo/.everlingo/workspaces/default",
            "mode": "rw",
        },
    },
    detach=True,
)
```

不设 `ports`——ws-container 仅靠 docker network alias 可达，不对宿主映射端口。复用现有 [container-spec.md](../deploy/image/container-spec.md) 镜像（entrypoint.sh + indexer + gateway 二进程不变）。

backend_url = `http://everlingo-<user_name>-<short_id>:8000`。

## 7. ws-container 生命周期（状态机）

```
                 ┌──────────┐
   ws add ──────▶│ absent   │
                 └────┬─────┘
                      │ docker create
                      ▼
                 ┌──────────┐  create 失败/异常
                 │ creating │──────────────▶ ┌───────┐
                 └────┬─────┘                │ error │
                      │ docker start         └───────┘
                      ▼
                 ┌──────────┐  start 失败/探活超时
                 │ starting │──────────────▶ │ error │
                 └────┬─────┘
                      │ 探活通过
                      ▼
                 ┌──────────┐  探活失败/容器消失 ──▶ stopped
   idle timeout ─▶│ started  │
                 └────┬─────┘
                      │ docker stop（不 remove）
                      ▼
                 ┌──────────┐  docker start ──▶ starting
   ws start ────▶│ stopped  │
                 └──────────┘
   ws rm --purge: docker remove + 删 host_workspace_dir + 删行
```

状态取值：`absent / creating / starting / started / stopped / error`。

### 7.1 并发控制

`creating` / `starting` 期间，同一 `ws_container_id` 的并发 backend 请求等待结果或返回 503，**不重复**调 docker。用进程内 `asyncio.Lock(per ws_container_id)` + DB status 双保险。

### 7.2 lazy 启动

```
WS-Router GET /internal/users/{uid}/default-ws/backend
        │
        ▼
   WS-Master 查 ws_containers 表（is_default=1）
        │
        ├── started + 健康 ──────────────▶ 返回 URL
        │
        ├── stopped ──▶ docker start ──▶ 探活 ──▶ 返回 URL
        │
        └── absent  ──▶ docker create+start ─▶ 探活 ─▶ 返回 URL

  [后台 task 每 healthcheck_interval]
        │
        ▼
   遍历 status=started 的 ws-container
        │
        ├── 探活失败 → 标记 stopped
        └── SSE client 数为 0 持续 > idle_timeout → docker stop（不 remove，保留 workspace）
```

- `docker stop` 保留 `ws_containers` 表记录与 `status=stopped`，下次请求直接 `docker start`（容器对象仍在）。
- `docker remove` 仅在 `ws rm --purge` 时调用，并删除 `host_workspace_dir`（需 `--purge` 确认）。

### 7.3 WS-Master 启动对账

WS-Master 启动时遍历 `ws_containers` 中 `status ∈ {creating, starting, started}` 的行，按 `docker_container_id` / `container_name` 查 docker 实际状态回写：

- 容器不存在 → `absent`
- 容器存在但未运行 → `stopped`
- 容器运行 + 探活通过 → `started`
- 容器运行但探活失败 → `error`（由 healthcheck task 后续处理）

防止 Master 重启后 DB 与 docker 实际状态不一致。

## 8. CLI

`everlingo ws_master <subcommand>`，运维用：

| 命令 | 说明 |
|---|---|
| `user add --name mark --display-name "Mark"` | 创建用户，交互输入密码；**同时创建 default ws-container**（status=absent，首次访问时 lazy create） |
| `user list` | 列出所有用户 |
| `user rm --name mark [--purge]` | 删除用户；`--purge` 同时 stop+remove 所有 ws-container 并删 host 目录 |
| `ws add --user mark` | 新增 ws-container；Phase 1 该 user 已有 ws 则拒绝（`max_ws_per_user` 超限） |
| `ws list [--user mark]` | 列出 ws-container 状态 |
| `ws rm --id <ws_id> [--purge]` | 删除 ws-container；`--purge` stop+remove 容器并删 host 目录 |
| `ws start --id <ws_id>` | 强制拉起 |
| `ws stop --id <ws_id>` | 强制停机 |
| `ws set-default --id <ws_id>` | 切换默认 ws-container（Phase 1 仅一个，预留） |
| `pat add --user mark --label "curl-laptop" [--expires 365d]` | 生成 PAT，明文打印一次 |
| `pat list --user mark` | 列出 PAT（只显示 id/label/created/last_used/expires，不含明文） |
| `pat rm --id <pat_id>` | 吊销 PAT |
| `identity list --user mark` | 列出该 user 已绑定的外部 IdP 身份（provider/subject/email/last_used） |
| `identity unlink --id <identity_id>` | 解绑某个外部身份（仅删 `user_identities` 行，不删 user） |

> SSO 身份**绑定**通过 OAuth flow 在线完成（WS-Router 侧 `GoogleSSOAuthProvider` 等回调时写入 `user_identities`），不经 CLI。CLI 仅提供查询与解绑。Phase 1 仅 `password` provider 启用，无 SSO 数据；Phase 2+ 启用 SSO provider 后 CLI 可用。

CLI 直连 `ws_master.sqlite`，不走 internal API。

## 9. 镜像

`docs/impl-spec/deploy/image/Dockerfile.ws_master`，单独精简构建（跳过 frontend-builder stage，无 `web/dist`）。详见 [deploy.md](./deploy.md) §镜像构建。

## 10. 关键不变量

- WS-Master 是 `ws_master.sqlite` 与 docker daemon 的唯一访问者；WS-Router 不直接访问二者。
- ws-container 不对宿主映射端口，仅靠 `everlingo-net` 内 alias 可达。
- WS-Master 不签发 WS-Router JWT；JWT 签发与验签在 WS-Router 侧（共享 `jwt_secret`）。
- `docker stop` 不删 workspace；只有显式 `ws rm --purge` 或 `user rm --purge` 才删。
- LLM 密钥不写入 workspace `everlingo.yaml`；经容器 env 注入，依赖 `config.py` env fallback。
- `user_name` 不可修改（用作容器名与 workspace 目录路径）。

