# 部署编排（WS-Master 模式）

- 状态：Planned（2026-07-29 修订）
- 相关文档：
  - [ws-router.md](./ws-router.md)
  - [ws-master.md](./ws-master.md)
  - [external-nginx.md](./external-nginx.md)
  - [ws-container-spec.md](../../deploy/ws-container/ws-container-spec.md)（workspace container 镜像规范）

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

compose 文件落地于仓库根 `docker-compose.yml`，示例配置与 nginx conf 落地于 `deploy/examples/`、`deploy/nginx/`（见 §5.4）。

```yaml
services:
  ws_router:
    image: ghcr.io/<owner>/everlingo-ws-router:0.1    # 或本地构建: everlingo-ws-router:0.1
    # ENTRYPOINT 已是 `python -m everlingo`（见 §5.2），command 只需补子命令 + config
    command: ["ws_router", "--config", "/etc/everlingo/ws_router.yaml"]
    ports:
      - "127.0.0.1:8100:8100"        # 仅 nginx 可达
    volumes:
      - "./deploy/examples/ws_router.yaml:/etc/everlingo/ws_router.yaml:ro"
    expose:
      - "8100"
    depends_on:
      - ws_master
    networks:
      - everlingo-net
    restart: unless-stopped

  ws_master:
    image: ghcr.io/<owner>/everlingo-ws-master:0.1    # 或本地构建: everlingo-ws-master:0.1
    # 同上，ENTRYPOINT 为 `python -m everlingo`
    command: ["ws_master", "--config", "/etc/everlingo/ws_master.yaml"]
    volumes:
      - "./deploy/examples/ws_master.yaml:/etc/everlingo/ws_master.yaml:ro"
      - "./deploy/examples/ws_container_everlingo_template.yaml:/etc/everlingo/ws_container_everlingo_template.yaml:ro"
      - "master-data:/root/.everlingo"
      - "/var/run/docker.sock:/var/run/docker.sock"
      - "${HOST_WS_DIR}:/workspaces"
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

> 变更说明：compose 服务名 `edge`→`ws_router`、`master`→`ws_master`（下划线，与源码包对齐）；镜像 tag 用连字符（docker 惯例）；新增 `ws_container_everlingo_template.yaml` 挂载；环境变量 `WORKSPACES_ROOT`→`HOST_WS_DIR`（与 `ws_master.yaml.host_ws_dir` 命名对齐）。**ENTRYPOINT / command 拆分**：Dockerfile `ENTRYPOINT` 仅固定基础调用 `python -m everlingo`，子命令与 `--config` 路径由 compose `command:` 提供，便于 compose 层覆盖运行参数（如临时换 config）而镜像保持通用。compose `volumes:` 相对路径以 compose 文件所在目录（仓库根）为基准，故示例配置挂载用 `./deploy/examples/...`。

## 3. 权限：WS-Master 访问 docker.sock

WS-Master 容器需要访问宿主 `/var/run/docker.sock`（DooD — Docker outside of Docker）：

1. 宿主查 docker 组 GID：`getent group docker | cut -d: -f3`
2. compose 环境注入：`export DOCKER_GID=$(getent group docker | cut -d: -f3)`
3. compose 中 `group_add: ["${DOCKER_GID}"]` 让 WS-Master 容器进程获得该组辅助 GID，从而可读写 socket

WS-Master 镜像内不预装 docker CLI；用 `docker` Python SDK 通过 `unix:///var/run/docker.sock` 访问。

## 4. Workspace 挂载策略

- 宿主侧 workspace 根：`${HOST_WS_DIR}`（如 `~/everlingo/workspaces`）
- WS-Master 容器挂载 `${HOST_WS_DIR}:/workspaces`，使容器内 `/workspaces` 指向宿主 `${HOST_WS_DIR}`
- `ws_master.yaml` 的两条路径：
  - `host_ws_dir: "${HOST_WS_DIR}"` — 宿主路径，WS-Master 写入 `ws_containers.host_workspace_dir` 作为 docker bind source
  - `container_ws_dir: "/workspaces"` — 容器内挂载点，WS-Master 用于 mkdir / copy template / rmtree 等文件操作
- WS-Master 创建 ws-container 时，volume bind source 使用 **`host_workspace_dir`**（宿主绝对路径），docker daemon 据此绑定宿主目录；文件操作在**容器路径**下完成，代码自动做前缀转换

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

复用现有 `deploy/ws-container/Dockerfile`（多阶段：frontend-builder + deps + runtime），产物含 `web/dist`。见 [ws-container-spec.md](../../deploy/ws-container/ws-container-spec.md)。WS-Master 配置 `master.image` 指向此镜像。

### 5.2 WS-Router 镜像

`deploy/ws-router/Dockerfile`，单独精简构建，跳过 frontend-builder stage（无 `web/dist`）。`ENTRYPOINT` 仅固定基础调用 `python -m everlingo`，子命令与 `--config` 由 compose `command:` 提供（见 §2）：

```dockerfile
# Stage: deps（与现有 Dockerfile 的 deps stage 一致）
FROM python:3.12.13-bookworm AS deps

ARG HTTP_PROXY
ARG HTTPS_PROXY
ENV HTTP_PROXY=$HTTP_PROXY
ENV HTTPS_PROXY=$HTTPS_PROXY

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
ENTRYPOINT ["python", "-m", "everlingo"]
```

> `HTTP_PROXY` / `HTTPS_PROXY` build-arg 与现有 ws-container Dockerfile 的 deps stage 对齐，代理环境传值可加速 `uv sync` 拉包；无代理环境传空值不影响构建。

```bash
DOCKER_BUILDKIT=1 docker buildx build . -f deploy/ws-router/Dockerfile  -t everlingo-ws-router:0.1
```

也可拉取 GHCR 发布的版本（见 [github-ci-spec.md](../../CI/github-ci-spec.md)）：

```bash
docker pull ghcr.io/<owner>/everlingo-ws-router:0.1.0
```

### 5.3 WS-Master 镜像

`deploy/ws-master/Dockerfile`，同 WS-Router 精简构建，`ENTRYPOINT` 为 `python -m everlingo`（子命令与 config 由 compose `command:` 提供，见 §2）：

```dockerfile
# Stage: deps（同上）
FROM python:3.12.13-bookworm AS deps

ARG HTTP_PROXY
ARG HTTPS_PROXY
ENV HTTP_PROXY=$HTTP_PROXY
ENV HTTPS_PROXY=$HTTPS_PROXY

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
ENTRYPOINT ["python", "-m", "everlingo"]
```

> 注：`pyproject.toml` 须含 `docker>=7.0` 与 `pyjwt>=2.8` 两个新依赖（见 PR1/PR2）。`HTTP_PROXY` / `HTTPS_PROXY` build-arg 同 §5.2 说明。

```bash
DOCKER_BUILDKIT=1 docker buildx build . -f deploy/ws-master/Dockerfile  -t everlingo-ws-master:0.1
```

也可拉取 GHCR 发布的版本（见 [github-ci-spec.md](../../CI/github-ci-spec.md)）：

```bash
docker pull ghcr.io/<owner>/everlingo-ws-master:0.1.0
```

### 5.4 示例配置与 nginx conf 落地

PR3 将以下示例文件落地到 `deploy/`（compose `volumes:` 相对路径以仓库根为基准）：

| 文件 | 内容来源 | compose 挂载目标 |
|---|---|---|
| `deploy/examples/ws_router.yaml` | [ws-router.md](./ws-router.md) §5 schema | `/etc/everlingo/ws_router.yaml` |
| `deploy/examples/ws_master.yaml` | [ws-master.md](./ws-master.md) §5.1 schema | `/etc/everlingo/ws_master.yaml` |
| `deploy/examples/ws_container_everlingo_template.yaml` | [ws-master.md](./ws-master.md) §5.2 模板 | `/etc/everlingo/ws_container_everlingo_template.yaml` |
| `deploy/nginx/everlingo.conf.example` | [external-nginx.md](./external-nginx.md) §3 配置示例 | 宿主 nginx `sites-available/`（运维手动复制） |

示例 yaml 中 secret 字段（`jwt_secret` / `master_secret` / `shared_secret`）以占位或注释指引运维用 `openssl rand -hex 32` 生成，不写明文。`deploy/examples/ws_container_everlingo_template.yaml` 为 `docs/impl-spec/multiple-users/ws_container_everlingo_template.yaml` 的部署副本（内容一致，放在 `deploy/` 便于 compose 直接挂载）。

### 5.5 `.dockerignore`

仓库根放 `.dockerignore`（Docker 只读取 build context root 下的这一个，不支持 per-Dockerfile `.dockerignore`，「按路径就近取用」为错误表述，已在源文件注释中修正）。排除与 ws-router/ws-master 构建无关的大目录，同时不影响 ws-container 构建：

```
web/node_modules/
web/dist/
extension/
docs/
tests/
mark-specific/
.git/
.venv/
node_modules/
*.md
.github/
.opencode/
.vscode/
README.assets/
```

> ws-router/ws-master 精简构建仅 `COPY pyproject.toml uv.lock`（deps stage）与 `COPY src/ src/`（runtime stage），上述目录均不参与构建。ws-container 需要 `web/` 但不需要 `web/node_modules/`（Stage1 自会 `npm ci` 重建）与 `web/dist/`（Stage1 自会 `npm run build` 现场生成），故排除二者而非整个 `web/`。三 Dockerfile 均以 `docker buildx build -f deploy/xxx/Dockerfile .` 从 repo root 构建，共用同一个 `.dockerignore`。

## 6. 部署步骤（运维参考）

```bash
# 1. 环境准备
export DOCKER_GID=$(getent group docker | cut -d: -f3)
export HOST_WS_DIR=$HOME/everlingo/workspaces
mkdir -p $HOST_WS_DIR

# 2. 构建 WS-Router / WS-Master 镜像
#    也可跳过本地构建，直接拉取 GHCR：docker pull ghcr.io/<owner>/everlingo-ws-router:0.1.0
#    代理环境下本地构建加 --build-arg HTTP_PROXY=... --build-arg HTTPS_PROXY=...
docker buildx build -f deploy/ws-router/Dockerfile \
  -t everlingo-ws-router:0.1 .
docker buildx build -f deploy/ws-master/Dockerfile \
  -t everlingo-ws-master:0.1 .

# 3. 生成 secret
openssl rand -hex 32 > /tmp/jwt_secret
openssl rand -hex 32 > /tmp/master_secret

# 4. 复制示例配置并填入 secret（示例见 deploy/examples/）
#    cp deploy/examples/ws_router.yaml ./deploy/examples/ws_router.yaml  # 就地编辑或复制到 compose 目录
#    在 ws_router.yaml 填入 jwt_secret / master_secret（步骤 3 生成的）
#    在 ws_master.yaml 填入 shared_secret（= master_secret）、openai_api_key 等
#    schema 参考 ws-router.md §5 / ws-master.md §5.1

# 5. 启动 compose
docker compose up -d

# 6. 创建用户与 PAT（同时创建 default ws-container，status=absent）
docker compose exec ws_master everlingo ws_master user add --name mark --display-name "Mark"
docker compose exec ws_master everlingo ws_master pat add --user mark --label "curl-laptop"

# 7. 配置 nginx（见 external-nginx.md），nginx -s reload
```

## 7. 单用户独立部署（对照）

上述为多用户 WS-Master 编排模式。单用户独立部署仍沿用 [ws-container-spec.md](../../deploy/ws-container/ws-container-spec.md) 的「经典部署方法」：单个 everlingo 容器直挂 workspace，nginx 或直接暴露端口。两条路线并存，按部署规模选择。
