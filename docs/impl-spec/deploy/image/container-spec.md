# Image 设计规范

## base image

runtime base image: `python:3.12.13-bookworm`

Dockerfile: docs/impl-spec/deploy/image/Dockerfile

## 镜像构建

采用多阶段构建，三个 stage：

### Stage 1: `frontend-builder`
- base: `node:20-bookworm-slim`
- `COPY web/package.json web/package-lock.json` → `npm ci`
- `COPY web/` → `npm run build`
- 产物: `/web/dist`（Web Chatbot + Vault Editor SPA）

### Stage 2: `deps`
- base: `python:3.12.13-bookworm`
- 安装 `uv`（`pip install uv`）
- `COPY pyproject.toml uv.lock` → `uv sync --frozen --no-dev --no-install-project` 生成 `/app/.venv`（跳过本地包安装，只装外部依赖）
- 产物: `/app/.venv`（含全部 Python 依赖 + unidic-lite 词典数据）

### Stage 3: `runtime`
- base: `python:3.12.13-bookworm`
- 创建 everlingo 用户（见下「Linux 主用户」节）
- `COPY --from=deps /app/.venv .venv`
- `COPY src/ src/`
- `COPY pyproject.toml ./`
- `COPY --from=frontend-builder /web/dist web/dist`
- `COPY docs/impl-spec/deploy/image/root/ /`（workspace 模板 + entrypoint.sh，路径相对 repo root；见下「app files」节）
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

## app files

### root 目录覆盖
把 docs/impl-spec/deploy/image/root 目录下的目录结构和文件写入 image 的 `/`。当前 root 目录结构：

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
URL=$(cat "$MCP_URL_FILE")
host_port=$(echo "$URL" | sed -E 's#https?://127\.0\.0\.1:([0-9]+).*#\1#')
while ! (echo > /dev/tcp/127.0.0.1/$host_port) 2>/dev/null; do
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
| indexer | `python -m everlingo mem indexer start` | SQLite 唯一写者；写 `$workspace/indexer.sock`（REST UDS）+ `$workspace/indexer.mcp.url`（MCP Streamable HTTP URL，绑 127.0.0.1 OS 端口）；见 memory-vault-search-spec.md「进程拓扑」 |
| gateway | `python -m everlingo gateway --channel_web` | Web Session Acceptor（FastAPI + 前端 SPA）；通过 `indexer.mcp.url` 发现 MCP server；见 gateway.md |

启动顺序：**indexer 必须先于 gateway 启动**（gateway 依赖 `indexer.mcp.url` 文件发现 MCP server URL，见 `mem_writer_mcp_client.py:_read_mcp_url`）。entrypoint.sh 通过轮询 `indexer.mcp.url` 文件出现 + `/dev/tcp` 端口连通探测保证此顺序。

进程退出：`wait -n` 等任一子进程退出即全退（容器最佳实践：避免 PID 1 在子进程死后僵尸）。stdout/stderr 不重定向，`docker logs` 可见双进程输出；日志同时写 `$workspace/logs/everlingo.log` 与 `indexer.log`。

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

## 经典部署方法

```bash
# 宿主侧多用户隔离的目录命名（与容器内 os_user 无关）
app_user_name=mark
os_user_name=everlingo
image=everlingo:v0.1

host_workspace=~/everlingo_workspaces/${app_user_name}
mkdir -p ${host_workspace}

# 查看配置模板
docker run --rm $image cat /home/everlingo/.everlingo/workspaces/default/everlingo.yaml

cat >${host_workspace}/everlingo.yaml <<"EOF"
sys_setting:
  openai_api_key: 'sk-or-v1-xyz'
  openai_base_url: 'https://openrouter.ai/api/v1'
  openai_model: 'deepseek/deepseek-v4-flash'
  openai_embedding_model: 'baai/bge-m3'
  logging_setting:
    log_file: ''
    log_level: debug
user_profile:
  language:
    interface_language: zh-CN #默认界面语言是中文
    target_language: en #默认目标学习语言是英文

plugins:
  channels:
    channel_web: # Web Session Acceptor 配置
      listener: # 监听地址
        port: 8000 # 默认 8000
        interface: 0.0.0.0  # 默认 localhost
      public_address: # 浏览器访问地址。如外网或 https 反向代理访问时配置
        base_url: https://<your_domain>:<your_port>
EOF

# 整目录挂载覆盖 default workspace
docker run -d \
  -p 8000:8000 \
  -v ${host_workspace}:/home/${os_user_name}/.everlingo/workspaces/default \
  ${image}
```

## Run build image
```bash
cd $everlingo_repo

DOCKER_BUILDKIT=1 docker buildx build . -f docs/impl-spec/deploy/image/Dockerfile


## proxy build if in China
cd $everlingo_repo

DOCKER_BUILDKIT=1 docker buildx build \
  --build-arg HTTP_PROXY=http://192.168.16.58:8118 \
  --build-arg HTTPS_PROXY=http://192.168.16.58:8118 \
  --build-arg NO_PROXY="localhost,127.0.0.1,192.168.16.58,192.168.16.*" \
   . -f docs/impl-spec/deploy/image/Dockerfile
```