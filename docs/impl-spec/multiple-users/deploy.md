# 部署编排（WS-Master 模式）

- 状态：Planned（2026-07-29 修订）
- 相关文档：
  - [ws-router.md](./ws-router.md)
  - [ws-master.md](./ws-master.md)
  - [external-nginx.md](./external-nginx.md)
  - [ws-container-spec.md](../deploy/image/ws-container-spec.md)（workspace container 镜像规范）

---

## 1. 拓扑

全容器化（nginx 除外，nginx 为宿主现有服务）：

```
                 host :443/:80
                      │
                 ┌────▼─────┐
                 │  nginx   │  (host service, TLS terminate)
                 └────┬─────┘
                      │ http  proxy_pass http://127.0.0.1:8100
   docker network     │  everlingo-net
   ┌──────────────────┼───────────────────────────────────┐
   │                  │                                    │
   │             ┌────▼──────┐    ┌──────────┐            │
   │             │ ws-router │──▶ │ ws-master │            │
   │             │ :8100     │http│ :8101     │            │
   │             └────┬──────┘    └────┬──────┘            │
   │                  │               │ /var/run/docker.sock│
   │                  │ http          ▼                     │
   │                  ▼          Docker daemon             │
   │   everlingo-<user>-<short>:8000  (WS-Master 动态创建)  │
   │   everlingo-<user2>-<short>:8000                       │
   └────────────────────────────────────────────────────────┘
```

- WS-Router 通过宿主 `127.0.0.1:8100` 接收 nginx 转发（`ports: ["127.0.0.1:8100:8100"]`）
- WS-Master 仅在 `everlingo-net` 内监听（`expose: ["8101"]`，不映射宿主端口）
- workspace container 由 WS-Master 动态 create/start，network=`everlingo-net`，alias=`everlingo-<user_name>-<short_id>`，**不**映射宿主端口

## 2. docker-compose.yml

```yaml
services:
  ws_router:
    image: everlingo-ws-router:0.1
    command: ["python", "-m", "everlingo", "ws_router", "--config", "/etc/everlingo/ws_router.yaml"]
    ports:
      - "127.0.0.1:8100:8100"        # 仅 nginx 可达
    volumes:
      - "./ws_router.yaml:/etc/everlingo/ws_router.yaml:ro"
    expose:
      - "8100"
    depends_on:
      - ws_master
    networks:
      - everlingo-net
    restart: unless-stopped

  ws_master:
    image: everlingo-ws-master:0.1
    command: ["python", "-m", "everlingo", "ws_master", "--config", "/etc/everlingo/ws_master.yaml"]
    volumes:
      - "./ws_master.yaml:/etc/everlingo/ws_master.yaml:ro"
      - "./ws_container_everlingo_template.yaml:/etc/everlingo/ws_container_everlingo_template.yaml:ro"
      - "master-data:/root/.everlingo"
      - "/var/run/docker.sock:/var/run/docker.sock"
      - "${HOST_WS_DIR}:${HOST_WS_DIR}"
    group_add:
      - "${DOCKER_GID}"              # 宿主 docker 组 GID
    expose:
      - "8101"
    networks:
      - everlingo-net
    restart: unless-stopped

networks:
  everlingo-net:
    name: everlingo-net

volumes:
  master-data:
```

> 变更说明：compose 服务名 `edge`→`ws_router`、`master`→`ws_master`（下划线，与源码包对齐）；镜像 tag 用连字符（docker 惯例）；新增 `ws_container_everlingo_template.yaml` 挂载；环境变量 `WORKSPACES_ROOT`→`HOST_WS_DIR`（与 `ws_master.yaml.host_ws_dir` 命名对齐）。

## 3. 权限：WS-Master 访问 docker.sock

WS-Master 容器需要访问宿主 `/var/run/docker.sock`（DooD — Docker outside of Docker）：

1. 宿主查 docker 组 GID：`getent group docker | cut -d: -f3`
2. compose 环境注入：`export DOCKER_GID=$(getent group docker | cut -d: -f3)`
3. compose 中 `group_add: ["${DOCKER_GID}"]` 让 WS-Master 容器进程获得该组辅助 GID，从而可读写 socket

WS-Master 镜像内不预装 docker CLI；用 `docker` Python SDK 通过 `unix:///var/run/docker.sock` 访问。

## 4. Workspace 挂载策略

- 宿主侧 workspace 根：`${HOST_WS_DIR}`（如 `~/everlingo/workspaces`），对应 `ws_master.yaml.master.host_ws_dir`
- WS-Master 容器挂载 `${HOST_WS_DIR}:${HOST_WS_DIR}`，使其能以宿主同路径访问 workspace 目录
- WS-Master 创建 ws-container 时，volume bind 使用**宿主侧绝对路径** `ws_container.host_workspace_dir`，该路径在 WS-Master 与 ws-container 间一致（因 WS-Master 也以相同路径挂载，docker daemon bind 路径解析为宿主路径）

### 4.1 宿主侧目录结构

```
<HOST_WS_DIR>/
  <user_name>/                       # user_name 不可修改（见 ws-master.md §4.1）
    <ws_container_id>/               # UUID
      everlingo.yaml                 # 由 ws_container_everlingo_template.yaml 拷贝初始化
      memory/
      logs/
      ...
    <ws_container_id_2>/             # Phase 1: 每 user 最多 1 个；未来放开
  <user_name_2>/
    <ws_container_id_3>/
```

新 ws-container 的 `host_workspace_dir` = `${HOST_WS_DIR}/<user_name>/<ws_container_id>/`。

## 5. 镜像构建

### 5.1 workspace container 镜像

复用现有 `docs/impl-spec/deploy/image/Dockerfile`（多阶段：frontend-builder + deps + runtime），产物含 `web/dist`。见 [ws-container-spec.md](../deploy/image/ws-container-spec.md)。WS-Master 配置 `master.image` 指向此镜像。

### 5.2 WS-Router 镜像

`docs/impl-spec/deploy/image/Dockerfile.ws_router`，单独精简构建，跳过 frontend-builder stage（无 `web/dist`）：

```dockerfile
# Stage: deps（与现有 Dockerfile 的 deps stage 一致）
FROM python:3.12.13-bookworm AS deps
RUN pip install uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Stage: runtime
FROM python:3.12.13-bookworm AS runtime
RUN useradd -m -u 1000 everlingo
COPY --chown=everlingo:everlingo --from=deps /app/.venv .venv/
COPY --chown=everlingo:everlingo src/ src/
COPY --chown=everlingo:everlingo pyproject.toml ./
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
USER everlingo
ENTRYPOINT ["python", "-m", "everlingo", "ws_router", "--config", "/etc/everlingo/ws_router.yaml"]
```

### 5.3 WS-Master 镜像

`docs/impl-spec/deploy/image/Dockerfile.ws_master`，同 WS-Router 精简构建，ENTRYPOINT 为 `ws_master`：

```dockerfile
# Stage: deps（同上）
FROM python:3.12.13-bookworm AS deps
RUN pip install uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Stage: runtime
FROM python:3.12.13-bookworm AS runtime
RUN useradd -m -u 1000 everlingo
COPY --chown=everlingo:everlingo --from=deps /app/.venv .venv/
COPY --chown=everlingo:everlingo src/ src/
COPY --chown=everlingo:everlingo pyproject.toml ./
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
# docker.sock 通常 root:docker，WS-Master 以 everlingo(1000) 身份靠 group_add 访问
USER everlingo
ENTRYPOINT ["python", "-m", "everlingo", "ws_master", "--config", "/etc/everlingo/ws_master.yaml"]
```

> 注：`pyproject.toml` 须含 `docker>=7.0` 与 `pyjwt>=2.8` 两个新依赖（见 PR1/PR2）。

## 6. 部署步骤（运维参考）

```bash
# 1. 环境准备
export DOCKER_GID=$(getent group docker | cut -d: -f3)
export HOST_WS_DIR=$HOME/everlingo/workspaces
mkdir -p $HOST_WS_DIR

# 2. 构建 WS-Router / WS-Master 镜像
docker buildx build -f docs/impl-spec/deploy/image/Dockerfile.ws_router \
  -t everlingo-ws-router:0.1 .
docker buildx build -f docs/impl-spec/deploy/image/Dockerfile.ws_master \
  -t everlingo-ws-master:0.1 .

# 3. 生成 secret
openssl rand -hex 32 > /tmp/jwt_secret
openssl rand -hex 32 > /tmp/master_secret

# 4. 写 ws_router.yaml / ws_master.yaml / ws_container_everlingo_template.yaml
#    （参考 ws-router.md / ws-master.md）

# 5. 启动 compose
docker compose up -d

# 6. 创建用户与 PAT（同时创建 default ws-container，status=absent）
docker compose exec ws_master everlingo ws_master user add --name mark --display-name "Mark"
docker compose exec ws_master everlingo ws_master pat add --user mark --label "curl-laptop"

# 7. 配置 nginx（见 external-nginx.md），nginx -s reload
```

## 7. 单用户独立部署（对照）

上述为多用户 WS-Master 编排模式。单用户独立部署仍沿用 [ws-container-spec.md](../deploy/image/ws-container-spec.md) 的「经典部署方法」：单个 everlingo 容器直挂 workspace，nginx 或直接暴露端口。两条路线并存，按部署规模选择。
