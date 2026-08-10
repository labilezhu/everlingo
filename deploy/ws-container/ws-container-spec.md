# Workspace Container Image 设计规范

## base image

runtime base image: `python:3.12-trixie`

Dockerfile: deploy/ws-container/Dockerfile

## 镜像构建

采用多阶段构建，三个 stage：

### Stage 1: `frontend-builder`
- base: `node:20-bookworm-slim`
- `COPY web/package.json web/package-lock.json` → `npm ci`
- `COPY web/` → `npm run build`
- 产物: `/web/dist`（Web Chatbot + Vault Editor SPA）

### Stage 2: `deps`
- base: `python:3.12-trixie`
- 安装 `uv`（`pip install uv`）
- `COPY pyproject.toml uv.lock` → `uv sync --frozen --no-dev --no-install-project` 生成 `/app/.venv`（跳过本地包安装，只装外部依赖）
- 产物: `/app/.venv`（含全部 Python 依赖 + unidic-lite 词典数据）

### Stage 3: `runtime`
- base: `python:3.12-trixie`
- 创建 everlingo 用户（见下「Linux 主用户」节）
- `COPY --chown=everlingo:everlingo --from=deps /app/.venv .venv/`
- `COPY --chown=everlingo:everlingo src/ src/`
- `COPY --chown=everlingo:everlingo pyproject.toml ./`
- `COPY --chown=everlingo:everlingo --from=frontend-builder /web/dist web/dist/`
- `COPY --chown=everlingo:everlingo deploy/ws-container/root/ /`（workspace 模板 + entrypoint.sh，路径相对 repo root；见下「app files」节）

注：所有 COPY 均添加 `--chown=everlingo:everlingo`，避免在最后出现一个 `RUN chown -R` 层。后者会使每次 `COPY src/` 变更时，整个 `/app`（含 300M+ .venv）的所有权元数据全量写进新层，导致 docker pull 重新下载大体积 layer。
- `WORKDIR /app`
- `ENV PATH="/app/.venv/bin:$PATH"`（使 `python` 直接指向 venv）
- `ENV PYTHONPATH="/app/src"`（因 deps stage 用 `--no-install-project`，无 editable .pth 指向 src，需显式添加）
- `ENV EVERLINGO_WORKSPACE_DIR=/home/everlingo/.everlingo/workspaces/default`（见 workspace.md 优先级：CLI > `EVERLINGO_WORKSPACE_DIR` env > `EVERLINGO_WORKSPACE` env > default。设此 env 使容器内命令无需 `--workspace-dir`）
- `EXPOSE 8000`
- `ENTRYPOINT ["/app/entrypoint.sh"]`

## Linux 主用户
username: everlingo
UID & GID: 1000

权限： 可以运行 sudo 。 可以 sudo apt 安装包。

## 系统依赖

runtime 镜像由 `deploy/deps-base/Dockerfile` 提供基础，在 `sudo` 之外额外预装以下系统包（见 deps-base runtime stage 的 `apt-get install`）：

- `git`：Memory Vault 版本控制与远端备份（docs/impl-spec/worksplace/vault-version-control.md）依赖 `git` CLI 做 commit / push / pull / rebase。缺失时版本管理功能降级关闭（启动探测 `git --version`）。
- `openssh-client`：ssh 协议的 git remote（如 `git@github.com:user/vault.git`）传输依赖 ssh client；`GIT_SSH_COMMAND` 注入见 vault-version-control.md §11.3。
- `ca-certificates`：https 协议的 git remote（`git push https://...`）做 TLS 验证依赖。

ws-master / ws-router 镜像共享同一 deps-base，故同样携带这些包（无害）。

## app files

### root 目录覆盖
把 deploy/ws-container/root 目录下的目录结构和文件写入 image 的 `/`。当前 root 目录结构：

```
root/
  app/
    entrypoint.sh          # 进程编排脚本（见下「image 进程」节）
  home/everlingo/.everlingo/workspaces/default/
    everlingo.yaml          # workspace 配置模板（仅作模板，部署时由宿主整目录挂载覆盖）
```

### 应用源码与依赖
由多阶段构建注入（见「镜像构建」节）：
- `/app/.venv` — Python 虚拟环境（含全部依赖 + unidic-lite 词典）
- `/app/src/everlingo/...` — 应用源码
- `/app/pyproject.toml`

### 前端构建产物
`/app/web/dist` — 由 frontend-builder 注入。`web_acceptor.py` 通过相对路径 `../../../web/dist`（相对 `src/everlingo/gateway/`）访问，镜像内保持 `src/everlingo/gateway/web_acceptor.py` 与 `web/dist` 的相对关系（WORKDIR `/app`）。

## 镜像内目录布局

```
/app/
  .venv/                   # Python 虚拟环境
  src/everlingo/...        # 应用源码
  pyproject.toml
  web/dist/                # 前端 SPA 构建产物
  entrypoint.sh            # 进程编排脚本（来自 root/app/entrypoint.sh，经 COPY root/ / 落到 /app/entrypoint.sh）
/home/everlingo/
  .everlingo/workspaces/default/
    everlingo.yaml         # 配置模板（部署时被整目录挂载覆盖）
```

WORKDIR: `/app`

## image 进程

容器启动时由 `/app/entrypoint.sh` 编排两个进程。命令统一使用 `python -m everlingo ...`（走 `__main__.py` → `main.py` dispatch，见 app-entry.md）。

### entrypoint.sh 职责

```bash
#!/usr/bin/env bash
set -euo pipefail

WS="${EVERLINGO_WORKSPACE_DIR:-/home/everlingo/.everlingo/workspaces/default}"
MCP_URL_FILE="$WS/indexer.mcp.url"
rm -f "$MCP_URL_FILE"  # 清理上一轮容器残留（indexer 被 SIGKILL/OOM 时 finally 不执行）

# 1. 后台启动 indexer
python -m everlingo mem indexer start &
idx_pid=$!

# 2. 等 indexer 就绪：轮询 indexer.mcp.url 出现并 URL 中端口可连
#    indexer.mcp.url 内容格式: http://127.0.0.1:<port>/mcp（见 server.py _run_indexer）
while [ ! -f "$MCP_URL_FILE" ]; do
  sleep 0.5
  if ! kill -0 "$idx_pid" 2>/dev/null; then
    echo "indexer exited before ready" >&2
    exit 1
  fi
done
while true; do
  URL=$(cat "$MCP_URL_FILE")
  host_port=$(echo "$URL" | sed -E 's#https?://127\.0\.0\.1:([0-9]+).*#\1#')
  if (echo > /dev/tcp/127.0.0.1/"$host_port") 2>/dev/null; then
    break
  fi
  sleep 0.5
  if ! kill -0 "$idx_pid" 2>/dev/null; then
    echo "indexer exited before ready" >&2
    exit 1
  fi
done

# 3. 后台启动 gateway
python -m everlingo gateway --channel_web &
gw_pid=$!

# 4. 任一子进程退出则全退（exit code 透传）
wait -n "$idx_pid" "$gw_pid"
exit_code=$?
kill "$idx_pid" "$gw_pid" 2>/dev/null || true
exit "$exit_code"
```

### 进程说明

| 进程 | 命令 | 职责 |
|---|---|---|
| indexer | `python -m everlingo mem indexer start` | SQLite 唯一写者；写 `$workspace/indexer.sock`（REST UDS）+ `$workspace/indexer.mcp.url`（MCP Streamable HTTP URL，默认 8100，端口冲突时退回 OS 分配）；见 memory-vault-search-spec.md「进程拓扑」 |
| gateway | `python -m everlingo gateway --channel_web` | Web Session Acceptor（FastAPI + 前端 SPA）；通过 `indexer.mcp.url` 发现 MCP server；见 gateway.md |

启动顺序：**indexer 必须先于 gateway 启动**（gateway 依赖 `indexer.mcp.url` 文件发现 MCP server URL，见 `mem_writer_mcp_client.py:_read_mcp_url`）。entrypoint.sh 通过轮询 `indexer.mcp.url` 文件出现 + `/dev/tcp` 端口连通探测保证此顺序。双重保险防 stale 文件：indexer 启动时 unlink 上轮残留的 `indexer.mcp.url`（`_run_indexer`），entrypoint.sh 启动 indexer 前 `rm -f` 做第二轮兜底。

进程退出：`wait -n` 等任一子进程退出即全退（容器最佳实践：避免 PID 1 在子进程死后僵尸）。stdout/stderr 不重定向，`docker logs` 可见双进程输出；日志同时写 `$workspace/logs/everlingo.log` 与 `indexer.log`。

## image 进程健康检查（healthz）

### 动机

WS-Master 的 lazy start 状态机（见 [ws-master.md](../../../docs/impl-spec/multiple-users/ws-master.md) §6.1/§7）依赖「探活通过」才能将 ws-container 从 `starting` 推进到 `started` 并返回 `backend_url`。容器在 entrypoint.sh 内仅做**容器内**的 indexer→gateway 顺序就绪探测（`/dev/tcp` 探 MCP 端口），**对外没有**可探活的 HTTP 端点。为此 gateway 侧实现一个轻量健康检查端点，供多用户编排（WS-Master 探活）与单用户部署的 docker `HEALTHCHECK` 共用。

### 端点

| Method | Path | 说明 |
|---|---|---|
| GET | `/healthz` | gateway 进程就绪自检 |

- **位置**：`src/everlingo/gateway/web_acceptor.py`，注册在 `app` 上，路由顺序在 catch-all `/{path:path}` **之前**（避免被吞）。与 session 路由同级。
- **成功** `200` `application/json`：
  ```json
  { "status": "ok" }
  ```
- **未就绪** `503` `application/json`：
  ```json
  { "status": "error", "reason": "gateway_not_initialized" | "indexer_not_ready" }
  ```
- **就绪判定**（本地同步、无网络 IO，不依赖外部超时）：
  - `_gateway` 未注入（acceptor 尚未初始化）→ 503 `gateway_not_initialized`
  - `indexer.mcp.url` 文件不存在（indexer 未就绪）→ 503 `indexer_not_ready`
  - 否则 → 200
- **不校验项**（刻意保持轻量）：
  - **不做 TCP 端口连通探测**——entrypoint.sh 已保证 gateway 启动时 indexer 端口连通；运行中崩溃由 WS-Master healthcheck task 轮询 healthz 兑底发现。
  - **不校验 LLM 可达性**——LLM 调用在请求时按需失败重试，不属于进程就绪范畴。
- **无鉴权**：`/healthz` 不经过认证中间件，任何来源均可探（仅返回 `status`/`reason`，无敏感信息）。
- **探活方**：
  - WS-Master：lazy start 后轮询 `http://<ws-container-alias>:8000/healthz`，200 即 `started`（见 [ws-master.md](../../../docs/impl-spec/multiple-users/ws-master.md) §6.1）。
  - docker `HEALTHCHECK`：见下。

### Dockerfile `HEALTHCHECK`

镜像已配置 `HEALTHCHECK` 指令（见 [Dockerfile](./Dockerfile)），用基础镜像自带的 `python` 调 `/healthz`：

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).read()" || exit 1
```

- `start-period=60s`：覆盖 indexer 冷启（加载 unidic-lite 词典 + sqlite 初始化）+ gateway 起步，避免启动期间被误判 unhealthy。
- `--interval=30s --retries=3`：启动后每 30s 探一次，连续 3 次失败才标 unhealthy。
- 单用户独立部署也受益：`docker ps` 可见 health 状态，配合 `restart: unless-stopped` 可容器自愈。

### 与 entrypoint.sh 就绪探测的关系

| 机制 | 作用域 | 用途 |
|---|---|---|
| entrypoint.sh `/dev/tcp` 探 indexer MCP 端口 | **容器内** | 保证 indexer 先于 gateway 启动（进程编排顺序） |
| `/healthz` 端点 | **容器外** | WS-Master / docker daemon 探活 gateway 是否就绪受理请求 |

两者互补，不重叠：entrypoint.sh 保证「进程拉起顺序」，`/healthz` 对外宣告「gateway 已可服务」。

## image expose port

8000（gateway Web Session Acceptor 监听端口，见 `everlingo.yaml` `channel_web.listener.port`）

## workspace 挂载策略

镜像内置 `~/.everlingo/workspaces/default/everlingo.yaml` 仅作**模板**。经典部署时，宿主侧准备好整个 workspace 目录（含 `everlingo.yaml`、`memory/`、`logs/` 等），整目录挂载覆盖容器内 default workspace 目录：

```
-v ${host_workspace}:/home/everlingo/.everlingo/workspaces/default
```

挂载后镜像内置模板被覆盖，容器使用宿主侧配置与数据。首次部署可从镜像取出模板参考：

```bash
docker run --rm everlingo:v0.1 cat /home/everlingo/.everlingo/workspaces/default/everlingo.yaml
```

## Run build image

```bash
cd $everlingo_repo

DOCKER_BUILDKIT=1 docker buildx build . -f deploy/ws-container/Dockerfile -t everlingo:0.0.1-rc.3


## proxy build if in China
cd $everlingo_repo

DOCKER_BUILDKIT=1 docker buildx build \
  --build-arg HTTP_PROXY=http://192.168.16.58:8118 \
  --build-arg HTTPS_PROXY=http://192.168.16.58:8118 \
  --build-arg NO_PROXY="localhost,127.0.0.1,192.168.16.58,192.168.16.*" \
   . -f deploy/ws-container/Dockerfile -t everlingo:0.0.1-rc.3
```

## 经典部署方法

```bash
# export OPENAI_API_KEY=
# export base_url_for_browser=https://<your_domain or host>:<your_port>
# image=ghcr.io/labilezhu/everlingo:0.0.1-rc.3

# 宿主侧多用户隔离的目录命名（与容器内 os_user 无关）
app_user_name=mark
os_user_name=everlingo
host_workspace=~/everlingo_workspaces/${app_user_name}

mkdir -p ${host_workspace}

# 查看配置模板
docker run --rm  --entrypoint /bin/bash $image -c 'cat /home/everlingo/.everlingo/workspaces/default/everlingo.yaml'

cat >${host_workspace}/everlingo.yaml << EOF
sys_setting:
  openai_api_key: "$OPENAI_API_KEY"
  openai_base_url: 'https://openrouter.ai/api/v1'
  openai_model: 'deepseek/deepseek-v4-flash-0731'
  openai_embedding_model: 'baai/bge-m3'
  logging_setting:
    log_file: ''
    log_level: debug
user_profile:
  language:
    interface_language: '' # 界面语言（可选）：留空时按 OS locale 推断，兜底 en；后续 onboarding 会让用户显式选择
    target_language: en #默认目标学习语言是英文

plugins:
  channels:
    channel_web: # Web Session Acceptor 配置
      listener: # 监听地址
        port: 8000 # 默认 8000
        interface: 0.0.0.0  # 默认 localhost
      public_address: # 浏览器访问地址。如外网或 https 反向代理访问时配置
        base_url: $base_url_for_browser
EOF

# 整目录挂载覆盖 default workspace
docker run -d \
  -p 8000:8000 \
  -v ${host_workspace}:/home/${os_user_name}/.everlingo/workspaces/default \
  --name everlingo -h everlingo \
  ${image}

tail -f ${host_workspace}/logs/*
```

## local build
```bash
# 本地开发兼容：Dockerfile 用 ARG DEPS_IMAGE 默认指向 ghcr，本地构建可传 --build-arg DEPS_IMAGE=everlingo-deps:local 配合本地 deploy/deps-base/Dockerfile 构建。
DOCKER_BUILDKIT=1 docker buildx build . -f deploy/deps-base/Dockerfile -t everlingo-deps:local
DOCKER_BUILDKIT=1 docker buildx build . -f deploy/ws-router/Dockerfile -t everlingo-ws-router:test --build-arg DEPS_IMAGE=everlingo-deps:local
DOCKER_BUILDKIT=1 docker buildx build . -f deploy/ws-master/Dockerfile -t everlingo-ws-master:test --build-arg DEPS_IMAGE=everlingo-deps:local
```