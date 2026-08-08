# User Authentication and Multi-User Deployment

Currently supports amd64 (Linux/Windows WSL PC) and arm64 (M-series MacOS Linux containers / Raspberry Pi).

Among these, I have actually tested amd64 Linux / arm64 Raspberry Pi.

## Topology

Fully containerized (except nginx, which is assumed to be an existing service on the host):

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
   │   everlingo-<user>-<short>:8000  (created dynamically by WS-Master)  │
   │   everlingo-<user2>-<short>:8000                       │
   └────────────────────────────────────────────────────────┘
```

- `WS-Router` receives nginx forwarding via the host `127.0.0.1:8100`
- `WS-Master` only listens inside the docker network `everlingo-net` (`expose: ["8101"]`, no host port mapping)
- `workspace container` is dynamically created/started by WS-Master, network=`everlingo-net`, alias=`everlingo-<user_name>-<short_id>`, **no** host port mapping

## WS-Router and WS-Master Container Deployment

```bash
######## base conf ########

export EVERLINGO_VER=0.1.1-rc.7

export OPENAI_API_KEY=<your_api_key>
export OPENAI_BASE_URL=https://openrouter.ai/api/v1
export OPENAI_MODEL=deepseek/deepseek-v4-flash
export OPENAI_EMBEDDING_MODEL=baai/bge-m3

export EVERLINGO_PUBLIC_BASE_URL=https://your_domain
# Source IP address used by Nginx when connecting to the Router. For security.
export WS_ROUTER_TRUSTED_PROXY_IP=127.0.0.1
# EverLingo service's external listen address (usually behind a reverse proxy)
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

# start compose


cd $DEPLOY_WORK_HOME

docker pull $WS_ROUTER_IMAGE
docker pull $WS_MASTER_IMAGE
docker pull $WORKSPLACE_IMAGE #speed up the first boot
export DOCKER_GID=$(getent group docker | cut -d: -f3)
export MASTER_SECRET=$(openssl rand -hex 32)
export JWT_SECRET=$(openssl rand -hex 32)
docker compose -p everctl up


##### Create user and pre-start workspace container #####

docker exec -it everctl-ws_master-1  python -m everlingo ws_master --config /etc/everlingo/ws_master.yaml user add --name $INIT_USER_NAME --display-name "$INIT_USER_NAME" --password $INIT_USER_PASSWORD

docker exec -it everctl-ws_master-1  python -m everlingo ws_master --config /etc/everlingo/ws_master.yaml ws start --user $INIT_USER_NAME

##### Generate a PAT token for the browser extension #### 

docker exec -it everctl-ws_master-1  python -m everlingo ws_master --config /etc/everlingo/ws_master.yaml pat add --user $INIT_USER_NAME --label chrome_ext


```

After success, visit:
http://$WS_ROUTER_HOST_LISTEN_ADDR
to test

## Reverse Proxy

Below is an example Nginx configuration:

```bash
sudo tee /etc/nginx/sites-available/home-everlingo <<"EOF"
server {
    listen 6457 ssl;
    listen [::]:6457 ssl;
    server_name <your_domain>

    ssl_certificate     /etc/nginx/cert.d/your_key.pem;
    ssl_certificate_key /etc/nginx/cert.d/your_key.key;

    # Proxy through to ws-router, for it to determine the cookie Secure bit / generate base_url / log
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_pass_request_headers on;    # proxy through Authorization: Bearer <token> (ws-router §3.1 programmatic client channel)

    # SSE: disable buffering + long timeout + HTTP/1.1 keep-alive (see §2.3)
    proxy_buffering    off;
    proxy_cache        off;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
    proxy_http_version 1.1;
    proxy_set_header   Connection "";

    client_max_body_size 10m;

    # Forward the full path to ws-router (:8100); ws-router then reverse-proxies per user to the backend ws-container
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
