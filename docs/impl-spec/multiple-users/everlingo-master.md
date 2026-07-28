# Master Service

- 状态：Planned（2026-07-28）
- 进程入口：`python -m everlingo master --config everlingo_master.yaml`（见 [app-entry.md](../app-entry.md)）
- 相关文档：
  - [edge.md](./edge.md)
  - [deploy.md](./deploy.md)
  - [external-nginx.md](./external-nginx.md)
  - [container-spec.md](../deploy/image/container-spec.md)（用户容器镜像规范）

---

## 1. 职责

Master 是多用户部署拓扑中的**后台编排服务**，运行于独立容器（见 [deploy.md](./deploy.md)）。它仅在 `everlingo-net` 内可达，不对公网暴露。负责：

- **数据所有者**：维护 `everlingo_master.sqlite` 的 `users` / `pat_tokens` / `containers` 三张表
- **认证校验后端**：校验用户名口令、校验 PAT
- **容器生命周期**：create / start / stop / remove 用户 everlingo 容器（lazy 启动 + idle 停机）
- **服务发现**：向 Edge 提供 `user_id → backend_url` 解析
- **CLI 运维**：用户增删、PAT 管理、容器查询

Master **不**反代用户流量、**不**面向公网、**不**签发 Edge 的 JWT（JWT 由 Edge 用共享 `jwt_secret` 本地签发与验签）。

## 2. 拓扑位置

```
Edge ──http──▶ Master(:8101, everlingo-net only)
                  │
                  │ docker SDK (unix:///var/run/docker.sock, 挂载)
                  ▼
              Docker daemon
                  │
                  │ create/start/stop (network=everlingo-net, alias=everlingo-<user>)
                  ▼
              everlingo-<user>:8000  (仅 everlingo-net 内可达)
```

Master 容器挂载宿主 `/var/run/docker.sock`，通过 `group_add` 注入宿主 docker GID 获得访问权限（见 [deploy.md](./deploy.md) §权限）。

## 3. 数据模型

数据库文件：`~/.everlingo/everlingo_master.sqlite`（Master 容器内挂载持久化 volume）。

### 3.1 `users`

| 字段 | 类型 | 说明 |
|---|---|---|
| `user_id` | TEXT PK | UUID |
| `user_name` | TEXT UNIQUE | 英文字母+下划线，用作容器名与 workspace 目录名 |
| `user_display_name` | TEXT | 展示名 |
| `password_hash` | TEXT | bcrypt 哈希 |
| `workspace_dir` | TEXT | 宿主侧绝对路径，如 `~/.everlingo/workspaces/mark` |
| `sso_subject` | TEXT NULL | 预留：Google SSO subject（未来） |
| `created_at` | TEXT | ISO8601 |

新用户 `workspace_dir` = `${workspace_workspaces}/${user_name}`，其中 `${workspace_workspaces}` 取自 `everlingo_master.yaml`。

### 3.2 `pat_tokens`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | TEXT PK | UUID |
| `user_id` | TEXT FK→users | |
| `token_hash` | TEXT | sha256(明文) |
| `label` | TEXT | 人类可读标签，如 `curl-laptop` |
| `created_at` | TEXT | |
| `last_used_at` | TEXT NULL | Edge 校验时回写 |
| `expires_at` | TEXT NULL | NULL = 永久 |

明文 token 生成时返回一次，不存储。

### 3.3 `containers`

| 字段 | 类型 | 说明 |
|---|---|---|
| `user_id` | TEXT PK FK→users | |
| `container_name` | TEXT | `everlingo-<user_name>` |
| `status` | TEXT | `running` / `stopped` / `absent` |
| `host_port` | TEXT NULL | 弃用（用户容器不对宿主映射端口）；保留字段 |
| `started_at` | TEXT NULL | |
| `last_seen_at` | TEXT NULL | 最近一次探活成功时间 |

## 4. 配置

`everlingo_master.yaml`：

```yaml
master:
  listen: 127.0.0.1:8101           # everlingo-net 内监听；容器内即 0.0.0.0:8101
  shared_secret: <random>          # X-Master-Token（与 edge.master_secret 一致）
  db: /root/.everlingo/everlingo_master.sqlite
  workspace_workspaces: /workspaces   # 宿主侧 workspace 根（容器内挂载点）

  image: ghcr.io/labilezhu/everlingo:0.0.1-rc.3
  network: everlingo-net
  openai_api_key: ${OPENAI_API_KEY}   # 注入用户容器 env
  openai_base_url: https://openrouter.ai/api/v1
  openai_model: deepseek/deepseek-v4-flash
  openai_embedding_model: baai/bge-m3

  idle_timeout: 1200                # 无 SSE client 持续秒数 → stop（默认 20 分钟）
  healthcheck_interval: 60          # 探活间隔秒数
  readiness_timeout: 60             # create/start 后等待 backend 就绪秒数
```

## 5. Internal API

Master 监听 `everlingo-net` 内 `master:8101`，所有请求校验头 `X-Master-Token: <shared_secret>`。未带或不符 → 401。

| Method | Path | 用途 |
|---|---|---|
| POST | `/internal/authenticate` | 入参 `{username, password}` → `{user_id}` 或 401 |
| GET | `/internal/users/{user_id}/backend` | lazy 拉起 + 返回 `{backend_url, status}` |
| POST | `/internal/users/{user_id}/ensure_started` | 强制拉起（即使 status=running 也探活） |
| POST | `/internal/pat/verify` | 入参 `{token}` → `{user_id}` 或 401；成功时回写 `last_used_at` |
| POST | `/internal/pat` | 入参 `{user_id, label, expires_at?}` → `{token, id}`（明文仅返回一次） |
| GET | `/internal/healthz` | 自检 |

### 5.1 `GET /internal/users/{user_id}/backend` 行为

1. 查 `containers` 表
2. `status=running` 且探活成功 → 返回 `http://everlingo-<user_name>:8000`
3. `status=stopped` → `docker start` → 探活就绪 → 返回 URL
4. 无记录或 `status=absent` → `docker create`（挂载 workspace_dir、注入 env、network=`everlingo-net`、alias=`everlingo-<user_name>`、不设 ports）→ `docker start` → 探活就绪 → 返回 URL
5. 探活失败超 `readiness_timeout` → 返回 503

### 5.2 创建用户容器参数

```python
docker.containers.create(
    image=master_config.image,
    name=f"everlingo-{user.user_name}",
    network=master_config.network,
    network_aliases=[f"everlingo-{user.user_name}"],
    environment={
        "OPENAI_API_KEY": master_config.openai_api_key,
        "OPENAI_BASE_URL": master_config.openai_base_url,
        "OPENAI_MODEL": master_config.openai_model,
        "OPENAI_EMBEDDING_MODEL": master_config.openai_embedding_model,
        "EVERLINGO_WORKSPACE_DIR": "/home/everlingo/.everlingo/workspaces/default",
    },
    volumes={
        user.workspace_dir: {
            "bind": "/home/everlingo/.everlingo/workspaces/default",
            "mode": "rw",
        },
    },
    detach=True,
)
```

不设 `ports`——用户容器仅靠 docker network alias 可达，不对宿主映射端口。复用现有 `container-spec.md` 镜像（entrypoint.sh + indexer + gateway 二进程不变）。

## 6. 容器生命周期（lazy）

```
Edge GET /internal/users/{uid}/backend
        │
        ▼
   Master 查 containers 表
        │
        ├── running + 健康 ──────────────▶ 返回 URL
        │
        ├── stopped ──▶ docker start ──▶ 探活 ──▶ 返回 URL
        │
        └── absent  ──▶ docker create+start ─▶ 探活 ─▶ 返回 URL

  [后台 task 每 healthcheck_interval]
        │
        ▼
   遍历 status=running 的容器
        │
        ├── 探活失败 → 标记 stopped
        └── SSE client 数为 0 持续 > idle_timeout → docker stop（不 remove，保留 workspace）
```

- `docker stop` 保留 `containers` 表记录与 `status=stopped`，下次请求直接 `docker start`（容器对象仍在）。
- `docker remove` 仅在用户删除（`everlingo master user rm`）时调用，并删除 workspace_dir（需 `--purge` 确认）。

## 7. CLI

`everlingo master <subcommand>`，运维用：

| 命令 | 说明 |
|---|---|
| `user add --name mark --display-name "Mark"` | 创建用户，交互输入密码，建 workspace_dir，写 users 表 |
| `user list` | 列出所有用户 |
| `user rm --name mark [--purge]` | 删除用户；`--purge` 同时 stop+remove 容器并删 workspace_dir |
| `pat add --user mark --label "curl-laptop" [--expires 365d]` | 生成 PAT，明文打印一次 |
| `pat list --user mark` | 列出 PAT（只显示 id/label/created/last_used/expires，不含明文） |
| `pat rm --id <pat_id>` | 吊销 PAT |
| `container list` | 列出容器状态 |
| `container start --user mark` | 强制拉起 |
| `container stop --user mark` | 强制停机 |

CLI 直连 `everlingo_master.sqlite`，不走 internal API。

## 8. 镜像

`docs/impl-spec/deploy/image/Dockerfile.master`，单独精简构建（跳过 frontend-builder stage，无 `web/dist`）。详见 [deploy.md](./deploy.md) §镜像构建。

## 9. 与 planning-discuss.md 的关系

`docs/planning-discuss.md:1-30` 早期设想为「单进程实例内多 workspace + user_id header 注入」路线。本设计采用「每用户独立容器 + Edge + Master」路线取代之。planning-discuss.md 其余 envelope 相关讨论与本设计无关，不受影响。

## 10. 关键不变量

- Master 是 `everlingo_master.sqlite` 与 docker daemon 的唯一访问者；Edge 不直接访问二者。
- 用户容器不对宿主映射端口，仅靠 `everlingo-net` 内 alias 可达。
- Master 不签发 Edge JWT；JWT 签发与验签在 Edge 侧（共享 `jwt_secret`）。
- `docker stop` 不删 workspace；只有显式 `user rm --purge` 才删。
