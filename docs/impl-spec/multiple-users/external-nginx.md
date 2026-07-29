# 外部 Nginx 配置

- 状态：Planned（2026-07-29 修订）
- 相关文档：
  - [ws-router.md](./ws-router.md)
  - [deploy.md](./deploy.md)

---

## 1. 定位

Nginx 是**宿主现有服务**，不在 docker compose 中。职责：

- 终止 TLS（HTTPS → HTTP）
- `proxy_pass` 到 WS-Router 容器暴露的宿主端口（默认 `127.0.0.1:8100`）
- 透传 `Authorization` 头与 `X-Forwarded-Proto`
- SSE 长连接配置（禁用缓冲、长读超时）

Nginx **不**负责认证、**不**做 user → backend 路由、**不**直连 ws-container。

## 2. 拓扑

```
Browser / curl / Chrome Extension
        │
        │ https
        ▼
   ┌─────────┐
   │  nginx  │  (host service, TLS terminate)
   └────┬────┘
        │ http  proxy_pass http://127.0.0.1:8100
        ▼
   WS-Router container (ports: 127.0.0.1:8100:8100)
```

## 3. 配置示例

```nginx
server {
    listen 443 ssl;
    server_name app.everlingo.com;

    ssl_certificate     /etc/letsencrypt/live/app.everlingo.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.everlingo.com/privkey.pem;

    # 透传给 Edge，用于判断 cookie Secure 位与生成 base_url
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto  $scheme;

    # 透传 Authorization（Bearer token）
    proxy_pass_request_headers on;

    # SSE 关键：禁用缓冲 + 长读超时
    proxy_buffering       off;
    proxy_cache           off;
    proxy_read_timeout    3600s;
    proxy_send_timeout    3600s;
    # HTTP/1.1 + keep-alive，支持 chunked 流式
    proxy_http_version    1.1;
    proxy_set_header      Connection "";

    client_max_body_size  10m;

    location / {
        proxy_pass http://127.0.0.1:8100;
    }
}

# 80 → 443 跳转
server {
    listen 80;
    server_name app.everlingo.com;
    return 301 https://$host$request_uri;
}
```

## 4. 关键指令说明

| 指令 | 值 | 原因 |
|---|---|---|
| `proxy_buffering` | `off` | SSE 事件需即时送达，缓冲会延迟 |
| `proxy_read_timeout` | `3600s` | SSE 长连接保持，避免 nginx 60s 默认超时断连 |
| `proxy_http_version` | `1.1` | 支持 chunked transfer + keep-alive |
| `Connection` | `""` | 启用 keep-alive 到 Edge |
| `X-Forwarded-Proto` | `$scheme` | WS-Router 据此设 cookie Secure 位（见 [ws-router.md](./ws-router.md) §trusted_proxy） |

## 5. WS-Router 侧配合

- WS-Router 配置 `ws_router.trusted_proxy: 127.0.0.1`（仅信任 nginx 来源 IP 的 `X-Forwarded-Proto`），防客户端伪造。
- WS-Router 容器 `ports: ["127.0.0.1:8100:8100"]`（仅监听宿主 loopback，不对外）。
- 若 WS-Router 与 nginx 同宿主，`127.0.0.1` 足够；若 nginx 在另一台机器，改为 nginx 可达的地址并收紧 `trusted_proxy`。

## 6. WebSocket（未来）

当前 chatbot 用 SSE，nginx 上述配置即可。若未来引入 WebSocket，需在对应 `location` 加：

```nginx
proxy_set_header Upgrade    $http_upgrade;
proxy_set_header Connection "upgrade";
```

目前不实现。
