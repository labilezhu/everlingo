# 部署编排（Master 模式）

- 状态：Planned（2026-07-28）
- 相关文档：
  - [edge.md](./edge.md)
  - [everlingo-master.md](./everlingo-master.md)
  - [external-nginx.md](./external-nginx.md)
  - [container-spec.md](../deploy/image/container-spec.md)（用户容器镜像规范）

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
   │             ┌────▼─────┐    ┌──────────┐              │
   │             │  edge    │──▶ │  master  │              │
   │             │ :8100    │http│ :8101    │              │
   │             └────┬─────┘    └────┬─────┘              │
   │                  │               │ /var/run/docker.sock│
   │                  │ http          ▼                     │
   │                  ▼          Docker daemon             │
   │   everlingo-<user> :8000  (Master 动态创建)            │
   │   everlingo-<user2> :8000                              │
   └────────────────────────────────────────────────────────┘
```

- Edge 通过宿主 `127.0.0.1:8100` 接收 nginx 转发（`ports: ["127.0.0.1:8100:8100"]`）
- Master 仅在 `everlingo-net` 内监听（`expose: ["8101"]`，不映射宿主端口）
- 用户容器由 Master 动态 create/start，network=`everlingo-net`，alias=`everlingo-<user_name>`，**不**映射宿主端口

## 2. docker-compose.yml

```yaml
services:
  edge:
    image: everlingo-edge:0.1
    command: ["python", "-m", "everlingo", "edge", "--config", "/etc/everlingo/edge.yaml"]
    ports:
      - "127.0.0.1:8100:8100"        # 仅 nginx 可达
    volumes:
      - "./edge.yaml:/etc/everlingo/edge.yaml:ro"
    expose:
      - "8100"
    depends_on:
      - master
    networks:
      - everlingo-net
    restart: unless-stopped

  master:
    image: everlingo-master:0.1
    command: ["python", "-m", "everlingo", "master", "--config", "/etc/everlingo/everlingo_master.yaml"]
    volumes:
      - "./everlingo_master.yaml:/etc/everlingo/everlingo_master.yaml:ro"
      - "master-data:/root/.everlingo"
      - "/var/run/docker.sock:/var/run/docker.sock"
      - "${WORKSPACES_ROOT}:${WORKSPACES_ROOT}"
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

## 3. 权限：Master 访问 docker.sock

Master 容器需要访问宿主 `/var/run/docker.sock`（DooD — Docker outside of Docker）：

1. 宿主查 docker 组 GID：`getent group docker | cut -d: -f3`
2. compose 环境注入：`export DOCKER_GID=$(getent group docker | cut -d: -f3)`
3. compose 中 `group_add: ["${DOCKER_GID}"]` 让 Master 容器进程获得该组辅助 GID，从而可读写 socket

Master 镜像内不预装 docker CLI；用 `docker` Python SDK 通过 `unix:///var/run/docker.sock` 访问。

## 4. Workspace 挂载策略

- 宿主侧 workspace 根：`${WORKSPACES_ROOT}`（如 `~/everlingo/workspaces`）
- Master 容器挂载 `${WORKSPACES_ROOT}:${WORKSPACES_ROOT}`，使其能以宿主同路径访问 workspace 目录
- Master 创建用户容器时，volume bind 使用**宿主侧绝对路径** `user.workspace_dir`（如 `/home/everlingo/workspaces/mark`），该路径在 Master 与用户容器间一致（因 Master 也以相同路径挂载，docker daemon bind 路径解析为宿主路径）

新用户 `workspace_dir` = `${WORKSPACES_ROOT}/${user_name}`。

## 5. 镜像构建

### 5.1 用户容器镜像

复用现有 `docs/impl-spec/deploy/image/Dockerfile`（多阶段：frontend-builder + deps + runtime），产物含 `web/dist`。见 [container-spec.md](../deploy/image/container-spec.md)。Master 配置 `master.image` 指向此镜像。

### 5.2 Edge 镜像

`docs/impl-spec/deploy/image/Dockerfile.edge`，单独精简构建，跳过 frontend-builder stage（无 `web/dist`）：

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
ENTRYPOINT ["python", "-m", "everlingo", "edge", "--config", "/etc/everlingo/edge.yaml"]
```

### 5.3 Master 镜像

`docs/impl-spec/deploy/image/Dockerfile.master`，同 Edge 精简构建，ENTRYPOINT 为 `master`：

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
# docker.sock 通常 root:docker，Master 以 everlingo(1000) 身份靠 group_add 访问
USER everlingo
ENTRYPOINT ["python", "-m", "everlingo", "master", "--config", "/etc/everlingo/everlingo_master.yaml"]
```

> 注：`pyproject.toml` 须含 `docker>=7.0` 与 `pyjwt>=2.8` 两个新依赖（见 PR1/PR2）。

## 6. 部署步骤（运维参考）

```bash
# 1. 环境准备
export DOCKER_GID=$(getent group docker | cut -d: -f3)
export WORKSPACES_ROOT=$HOME/everlingo/workspaces
mkdir -p $WORKSPACES_ROOT

# 2. 构建 Edge / Master 镜像
docker buildx build -f docs/impl-spec/deploy/image/Dockerfile.edge \
  -t everlingo-edge:0.1 .
docker buildx build -f docs/impl-spec/deploy/image/Dockerfile.master \
  -t everlingo-master:0.1 .

# 3. 生成 secret
openssl rand -hex 32 > /tmp/jwt_secret
openssl rand -hex 32 > /tmp/master_secret

# 4. 写 edge.yaml / everlingo_master.yaml（参考 edge.md / everlingo-master.md）

# 5. 启动 compose
docker compose up -d

# 6. 创建用户与 PAT
docker compose exec master everlingo master user add --name mark --display-name "Mark"
docker compose exec master everlingo master pat add --user mark --label "curl-laptop"

# 7. 配置 nginx（见 external-nginx.md），nginx -s reload
```

## 7. 单用户独立部署（对照）

上述为多用户 Master 编排模式。单用户独立部署仍沿用 [container-spec.md](../deploy/image/container-spec.md) 的「经典部署方法」：单个 everlingo 容器直挂 workspace，nginx 或直接暴露端口。两条路线并存，按部署规模选择。
