# 用户认证与多用户部署

当前支持 amd64(Linux/Windows WSL PC) 与 arm64( M系列的 MacOS 下的 Linux 容器 / Raspberry Pi )

其中，我已经实测的是 amd64 Linux / arm64 Raspberry Pi 。

## 拓扑

全容器化（nginx 除外，假设 nginx 为宿主现有服务）：

```
                 host :443
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

- `WS-Router` 通过宿主 `127.0.0.1:8100` 接收 nginx 转发
- `WS-Master` 仅在 docker network `everlingo-net` 内监听（`expose: ["8101"]`，不映射宿主端口）
- `workspace container` 由 WS-Master 动态 create/start，network=`everlingo-net`，alias=`everlingo-<user_name>-<short_id>`，**不**映射宿主端口

## WS-Router 与 WS-Master 容器部署

```bash
######## base conf ########

export EVERLINGO_VER=0.1.1-rc.7

export OPENAI_API_KEY=<your_api_key>
export OPENAI_BASE_URL=https://openrouter.ai/api/v1
export OPENAI_MODEL=deepseek/deepseek-v4-flash
export OPENAI_EMBEDDING_MODEL=baai/bge-m3

export EVERLINGO_PUBLIC_BASE_URL=https://your_domain
# Nginx 连接 到 Router 时，使用的源 IP 地址 。 用于安全
export WS_ROUTER_TRUSTED_PROXY_IP=127.0.0.1
# EverLingo 服务对外（一般是反向代理）的监听地址
export WS_ROUTER_HOST_LISTEN_ADDR=127.0.0.1:8100

export HOST_WS_DIR=<your_workspaces_dir_at_host>

export INIT_USER_NAME=<your_login_user_name>
export INIT_USER_PASSWORD=<your_login_user_password>

######## internal vars ########

export DEPLOY_WORK_HOME=~/deploy_home
export SRC_REPO_HOME=$DEPLOY_WORK_HOME/everlingo

export WORKSPLACE_IMAGE=ghcr.io/labilezhu/everlingo:${EVERLINGO_VER}
export WS_MASTER_IMAGE=ghcr.io/labilezhu/everlingo-ws-master:${EVERLINGO_VER}
export WS_ROUTER_IMAGE=ghcr.io/labilezhu/everlingo-ws-router:${EVERLINGO_VER}

####### build deploy home ########

mkdir $DEPLOY_WORK_HOME
cd $DEPLOY_WORK_HOME

git clone --branch v${EVERLINGO_VER} --depth 1 https://github.com/labilezhu/everlingo.git

cp $SRC_REPO_HOME/deploy/examples/* ./

######## run container #######

mkdir -p $HOST_WS_DIR

# 启动 compose


cd $DEPLOY_WORK_HOME

docker pull $WS_ROUTER_IMAGE
docker pull $WS_MASTER_IMAGE
docker pull $WORKSPLACE_IMAGE #speed up the first boot
export DOCKER_GID=$(getent group docker | cut -d: -f3)
export MASTER_SECRET=$(openssl rand -hex 32)
export JWT_SECRET=$(openssl rand -hex 32)
docker compose -p everctl up


##### 创建用户与 预启动 workspace container #####

docker exec -it everctl-ws_master-1  python -m everlingo ws_master --config /etc/everlingo/ws_master.yaml user add --name $INIT_USER_NAME --display-name "$INIT_USER_NAME" --password $INIT_USER_PASSWORD

docker exec -it everctl-ws_master-1  python -m everlingo ws_master --config /etc/everlingo/ws_master.yaml ws start --user $INIT_USER_NAME

##### 生成 浏览器扩展用的 PAT token #### 

docker exec -it everctl-ws_master-1  python -m everlingo ws_master --config /etc/everlingo/ws_master.yaml pat add --user $INIT_USER_NAME --label chrome_ext


```

成功后，访问网址：
http://$WS_ROUTER_HOST_LISTEN_ADDR
测试

## 反向代理

以下是一个 Nginx 示例配置：

```bash
sudo tee /etc/nginx/sites-available/home-everlingo <<"EOF"
server {
    listen 6457 ssl;
    listen [::]:6457 ssl;
    server_name <your_domain>

    ssl_certificate     /etc/nginx/cert.d/your_key.pem;
    ssl_certificate_key /etc/nginx/cert.d/your_key.key;

    # 透传给 ws-router，供其判断 cookie Secure 位 / 生成 base_url / 日志
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_pass_request_headers on;    # 透传 Authorization: Bearer <token>（ws-router §3.1 程序化客户端通道）

    # SSE：禁缓冲 + 长超时 + HTTP/1.1 keep-alive（见 §2.3）
    proxy_buffering    off;
    proxy_cache        off;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
    proxy_http_version 1.1;
    proxy_set_header   Connection "";

    client_max_body_size 10m;

    # 全路径透传到 ws-router（:8100）；ws-router 内部再按 user 反代到后端 ws-container
    location / {
        proxy_pass http://your_local_ip_running_ws_router:8100;
    }
}
EOF
```

```bash
sudo ln -s /etc/nginx/sites-available/home-everlingo /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```



## Clean up

```bash
cd $DEPLOY_WORK_HOME
docker compose -p everctl down

docker ps -aq --filter label=app=everlingo | xargs -r docker rm -f

docker network rm everlingo-net

# rm -rf $HOST_WS_DIR
# rm -rf $DEPLOY_WORK_HOME/*
```