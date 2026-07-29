# Edge Service

- 状态：Planned（2026-07-28）
- 进程入口：`python -m everlingo edge --config edge.yaml`（见 [app-entry.md](../app-entry.md)）
- 相关文档：
  - [everlingo-master.md](./everlingo-master.md)
  - [external-nginx.md](./external-nginx.md)
  - [deploy.md](./deploy.md)
  - [web-session-acceptor.md](../web-session-acceptor.md)
  - [reverse-poxy-auth.md](../auth/reverse-poxy-auth.md)（旧 Basic Auth 路线，已废弃）

---

## 1. 职责

Edge 是多用户部署拓扑中的**前台反代 + 认证服务**，运行于独立容器（见 [deploy.md](./deploy.md)）。它面向公网（经现有 nginx 反代），负责：

- 对外暴露登录页与 `POST /login`
- 校验请求凭证（Cookie 与 `Authorization: Bearer <token>`）
- 按 `user_id` 解析后端 everlingo 容器地址并反向代理（含 SSE 流式透传）
- **不**负责 TLS（由现有 nginx 终止）、**不**负责用户容器生命周期（由 Master 负责）、**不**直接访问 sqlite 或 docker daemon

## 2. 拓扑位置

```
Browser / curl / Chrome Extension
        │
        │ https
        ▼
   ┌─────────┐
   │  nginx  │  TLS terminate（宿主现有服务，非容器）
   └────┬────┘
        │ http (proxy_pass http://127.0.0.1:8100)
        │ docker network: everlingo-net
   ┌────▼─────┐         ┌──────────┐
   │  edge    │──http──▶│  master  │
   │ :8100    │         │ :8101    │
   └────┬─────┘         └────┬─────┘
        │ http                │ docker.sock
        ▼                     ▼
   everlingo-<user>:8000   (Master 动态创建)
```

Edge 通过宿主 `127.0.0.1:8100` 接收 nginx 转发；Master 与用户容器仅在 `everlingo-net` 内可达，不映射宿主端口。

## 3. 认证方案

Edge 支持两种凭证，中间件按优先级依次尝试：

### 3.1 双通道

| 通道 | 用途 | 存储 |
|---|---|---|
| Cookie `everlingo_sess` | 浏览器 SPA（Web Chatbot / Vault Editor） | httpOnly + Secure + SameSite=Lax |
| `Authorization: Bearer <token>` | Chrome Extension / curl / 程序化 API | 客户端自管（extension storage / 环境变量） |

### 3.2 两类 token

- **Session token（短期，JWT）**：`POST /login` 成功后签发，载荷 `{sub: user_id, exp, jti}`，HS256 签名，密钥 `edge.jwt_secret`。TTL 默认 8h。Edge **本地验签**，无需每请求查 Master。登录响应同时返回 body 与 Set-Cookie。
- **Personal Access Token（长期，PAT）**：用户在 Master CLI 或 UI 生成，明文仅展示一次，Master 以 `sha256` 哈希存 `pat_tokens` 表。Edge 收到 Bearer → 先本地 JWT 验签；失败再 POST Master `/internal/pat/verify`（带 TTL 缓存）。PAT 无固定过期或远期过期，可吊销。

### 3.3 中间件链

```
trusted_proxy  →  auth_middleware  →  backend_resolve  →  proxy
```

1. **trusted_proxy**：仅信任 nginx 来源 IP 与 `X-Forwarded-Proto`（配置 `edge.trusted_proxy`），据此决定 cookie Secure 位，防客户端伪造。
2. **auth_middleware**：
   - 读 `Authorization: Bearer <t>` → JWT 本地 HS256 验签成功则注入 `request.state.user_id`；否则调 Master `/internal/pat/verify`（带缓存）。
   - 无 Bearer → 读 cookie `everlingo_sess` → JWT 验签。
   - 均无且路径非 `/login*`、`/login/google*`（预留） → 401（`WWW-Authenticate: Bearer realm="everlingo"`）。浏览器端由前端拦截后跳 `/login`；程序化客户端返回 JSON。
3. **backend_resolve**：`GET Master /internal/users/{user_id}/backend` 取 `{backend_url, status}`，LRU 缓存 TTL=60s。Master 内部触发 lazy start（见 [everlingo-master.md](./everlingo-master.md) §容器生命周期）。
4. **proxy**：`httpx.AsyncClient` 反代到 `backend_url`，SSE 端点用 `client.stream("GET", ...)`。剔除 `Cookie` / `Authorization` / hop-by-hop 头；注入 `X-Everlingo-User: <user_id>`。

### 3.4 AuthProvider 抽象（预留 SSO）

```python
class AuthProvider(Protocol):
    async def login(self, request) -> User: ...
    async def authenticate(self, request) -> User | None: ...
    def login_routes(self) -> APIRouter: ...
```

- `PasswordAuthProvider`（Phase 1）：用户名+口令，校验委派 Master `/internal/authenticate`。
- `GoogleSSOAuthProvider`（Phase 2 预留）：OAuth2 Authorization Code + PKCE，回调换 id_token，注入相同 JWT。仅新增一个 Provider 子类，Edge 主管线不变。

配置 `edge.auth.providers` 为列表，未来可同时启用 password + google_sso。

### 3.5 Google SSO 兼容路径（Phase 2）

方案 A（服务端渲染登录页）对 Google SSO 完全兼容，无需改架构：

1. 登录页加一个「Sign in with Google」按钮 → `GET /login/google`
2. Edge 走 OAuth2 Authorization Code + PKCE 流程：
   - 重定向到 Google 授权页（`scope=openid email profile`）
   - 用户授权后 Google 回调 `GET /login/google/callback?code=...`
   - Edge 用 code 换 id_token / access_token
   - 从 id_token 取 `sub` 作为 `sso_subject` → 查 Master `users.sso_subject` 字段（已预留，见 [everlingo-master.md](./everlingo-master.md) §3.1）
   - 命中用户 → 签发与密码登录**相同**的 JWT（HS256, sub=user_id）→ Set-Cookie + 302 `/`
   - 未命中 → 首次登录可自动建用户（写入 `users.sso_subject`），或拒绝并提示联系管理员
3. SSO 成功后签发的 JWT 与密码登录走同一条 `auth_middleware`，下游 backend 反代逻辑零改动。

**为什么方案 A 不阻碍 SSO**：
- 登录页是 Edge 服务端渲染，加一个按钮和一条 OAuth redirect 很简单，不需要前端构建
- 登录页 HTML 极简（一个 form + 少量 CSS），加按钮无负担
- `AuthProvider` Protocol 抽象让 password 与 google_sso 可并存

**Phase 2 待决策（不阻塞 Phase 1）**：
- 首次 Google 登录是否自动建用户（自助注册）还是需要管理员预建
- 是否支持多 SSO provider 并存（Google + GitHub 等）

Phase 1 只需保证 `AuthProvider` 抽象与 `users.sso_subject` 字段存在即可。

## 4. 路由

### 4.1 Edge 自有路由

| Method | Path | 说明 |
|---|---|---|
| GET / POST | `/login` | 登录页（HTML 表单）/ 提交凭证 |
| GET | `/logout` | 清 cookie，302 `/login` |
| GET | `/me` | 返回 `{user_id, user_name, display_name}` |
| GET | `/login/google` | （预留）重定向到 Google OAuth |
| GET | `/login/google/callback` | （预留）OAuth 回调 |

### 4.2 反代路由（透传到后端容器）

`/`、`/editor`、`/api/session/...`、`/api/session/{id}/events`（SSE）、`/manifest.webmanifest` 等全部透传。后端 everlingo 容器内的 `web_acceptor.py` 逻辑不变（见 [web-session-acceptor.md](../web-session-acceptor.md)）。

### 4.3 登录页（HTML）

Edge 镜像是精简构建（**无 `web/dist`**，见 [deploy.md](./deploy.md) §5.2），不能复用现有前端 SPA。主 SPA 由后端 everlingo 容器提供（`/` 反代过去）。因此登录页必须由 Edge 自己提供，采用**服务端渲染最小 HTML**（无前端构建依赖）。

- `GET /login` → 返回 HTML 登录表单（含 username/password 输入框、提交按钮）。HTML 模板可硬编码在 Edge 代码或 `src/everlingo/edge/templates/login.html`，极简 CSS。
- `POST /login` → 校验凭证：
  - 成功 → Set-Cookie + 302 `/`（浏览器跳到主 SPA）
  - 失败 → 返回表单 + 错误提示
- `GET /logout` → 清 cookie + 302 `/login`

**未认证访问的分流**（`auth_middleware`）：

| 客户端 | 判定 | 响应 |
|---|---|---|
| 浏览器 | `Accept: text/html` 且无凭证 | 302 `/login` |
| 程序化 | 带 `Authorization` 或 `Accept: application/json` | 401 JSON（`WWW-Authenticate: Bearer realm="everlingo"`） |

**Chrome Extension 登录**：Extension 不走登录页，而是通过 Extension Options 配置 Token 字段（PAT 或 access_token），或弹窗内放「登录」按钮调 Edge `POST /login` 拿 access_token 存起来。详见 PR4（Chrome Extension Token 化）。

### 4.4 登录 API 响应

`POST /login` 同时支持表单提交（浏览器）与 JSON 提交（程序化客户端）：

```
POST /login
  表单：Content-Type: application/x-www-form-urlencoded
       username=...&password=...
  或 JSON：Content-Type: application/json
          {"username": "...", "password": "..."}

成功（程序化 / Accept: application/json）→ 200 {
    "user_id": "...",
    "access_token": "<jwt>",
    "token_type": "bearer",
    "expires_at": "2026-07-28T20:00:00Z"
  }
  Set-Cookie: everlingo_sess=<jwt>; HttpOnly; Secure; SameSite=Lax

成功（浏览器 / Accept: text/html）→ 302  /
  Set-Cookie: everlingo_sess=<jwt>; HttpOnly; Secure; SameSite=Lax

失败 → 401（程序化）或 表单 + 错误提示（浏览器）
```

- 浏览器：依赖 cookie，body 中 access_token 可忽略。
- Chrome Extension / curl：取 body 中 access_token 存起来，后续请求加 `Authorization: Bearer <access_token>`。

### 4.5 CORS

Chrome Extension origin（`chrome-extension://<id>`）请求 Edge 属跨源。Edge 配置：

```python
CORSMiddleware(
    allow_origins=edge.cors_allow_origins,   # 扩展 ID 白名单（读 edge.yaml）
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=False,                # 不依赖 cookie 凭据
)
```

因程序化客户端用 `Authorization` 头而非 cookie，`allow_credentials=False` 即可。CORSMiddleware 自动处理 OPTIONS 预检。

## 5. 配置

`edge.yaml`：

```yaml
edge:
  listen: 0.0.0.0:8100
  base_url: https://app.everlingo.com
  trusted_proxy: 127.0.0.1          # 仅信任 nginx 来源

  master_url: http://master:8101
  master_secret: <random>           # 与 master.shared_secret 一致，注入 X-Master-Token

  jwt_secret: <random>             # HS256 签名密钥
  session_ttl: 28800               # 8h
  backend_cache_ttl: 60            # backend URL LRU 缓存秒数
  pat_verify_cache_ttl: 30         # PAT 校验结果缓存秒数

  cors_allow_origins:
    - chrome-extension://<extension-id>

  auth:
    providers: [password]           # password | google_sso（预留）
    google_sso:                     # 预留，启用前为空
      client_id:
      client_secret:
      redirect_uri:
```

## 6. 镜像

`docs/impl-spec/deploy/image/Dockerfile.edge`，单独精简构建（跳过 frontend-builder stage，无 `web/dist`）。详见 [deploy.md](./deploy.md) §镜像构建。

## 7. 关键不变量

- Edge 永远不直接读 `everlingo_master.sqlite`，也不调 docker daemon；user → backend 的解析与容器生命周期一律委派 Master。
- Edge 可水平扩展多副本（共享 `jwt_secret` / `master_secret` 即可），无状态。
- TLS 永远不在 Edge 终止；cookie Secure 位依据 `X-Forwarded-Proto`。
