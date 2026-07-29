# WS-Router Service

- 状态：Planned（2026-07-29 修订）
- 进程入口：`python -m everlingo ws_router --config ws_router.yaml`（见 [app-entry.md](../app-entry.md)）
- 相关文档：
  - [ws-master.md](./ws-master.md)
  - [external-nginx.md](./external-nginx.md)
  - [deploy.md](./deploy.md)
  - [web-session-acceptor.md](../web-session-acceptor.md)
  - [reverse-poxy-auth.md](../auth/reverse-poxy-auth.md)（旧 Basic Auth 路线，已废弃）

---

## 1. 职责

WS-Router 是多用户部署拓扑中的**前台反代 + 认证服务**，运行于独立容器（见 [deploy.md](./deploy.md)）。它面向公网（经现有 nginx 反代），负责：

- 对外暴露登录页与 `POST /login`
- 校验请求凭证（Cookie 与 `Authorization: Bearer <token>`）
- 按 `user_id` 解析后端 workspace container 地址并反向代理（含 SSE 流式透传）
- **不**负责 TLS（由现有 nginx 终止）、**不**负责 ws-container 生命周期（由 WS-Master 负责）、**不**直接访问 sqlite 或 docker daemon

> 变更说明：原 `edge` 服务重命名为 `ws-router`（workspace container router），语义对齐 `workspace container` 核心概念（见 [ws-master.md](./ws-master.md) §2）。职责不变。

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
   ┌────▼──────┐         ┌──────────┐
   │ ws-router │──http──▶│ ws-master │
   │ :8100     │         │ :8101     │
   └────┬──────┘         └────┬──────┘
        │ http                 │ docker.sock
        ▼                      ▼
   everlingo-<user>-<short>:8000   (WS-Master 动态创建)
```

WS-Router 通过宿主 `127.0.0.1:8100` 接收 nginx 转发；WS-Master 与 ws-container 仅在 `everlingo-net` 内可达，不映射宿主端口。

## 3. 认证方案

WS-Router 支持两种凭证，中间件按优先级依次尝试：

### 3.1 双通道

| 通道 | 用途 | 存储 |
|---|---|---|
| Cookie `everlingo_sess` | 浏览器 SPA（Web Chatbot / Vault Editor） | httpOnly + Secure + SameSite=Lax |
| `Authorization: Bearer <token>` | Chrome Extension / curl / 程序化 API | 客户端自管（extension storage / 环境变量） |

### 3.2 两类 token

- **Session token（短期，JWT）**：`POST /login` 成功后签发，载荷 `{sub: user_id, exp, jti}`，HS256 签名，密钥 `ws_router.jwt_secret`。TTL 默认 8h。WS-Router **本地验签**，无需每请求查 WS-Master。登录响应同时返回 body 与 Set-Cookie。
- **Personal Access Token（长期，PAT）**：用户在 WS-Master CLI 或 UI 生成，明文仅展示一次，WS-Master 以 `sha256` 哈希存 `pat_tokens` 表。WS-Router 收到 Bearer → 先本地 JWT 验签；失败再 POST WS-Master `/internal/pat/verify`（带 TTL 缓存）。PAT 无固定过期或远期过期，可吊销。

### 3.3 中间件链

```
trusted_proxy  →  auth_middleware  →  backend_resolve  →  proxy
```

1. **trusted_proxy**：仅信任 nginx 来源 IP 与 `X-Forwarded-Proto`（配置 `ws_router.trusted_proxy`），据此决定 cookie Secure 位，防客户端伪造。
2. **auth_middleware**：
   - 读 `Authorization: Bearer <t>` → JWT 本地 HS256 验签成功则注入 `request.state.user_id`；否则调 WS-Master `/internal/pat/verify`（带缓存）。
   - 无 Bearer → 读 cookie `everlingo_sess` → JWT 验签。
   - 均无且路径非 `/login*`、`/login/google*`（预留） → 401（`WWW-Authenticate: Bearer realm="everlingo"`）。浏览器端由前端拦截后跳 `/login`；程序化客户端返回 JSON。
3. **backend_resolve**：`GET WS-Master /internal/users/{user_id}/default-ws/backend` 取 `{ws_container_id, backend_url, status}`，LRU 缓存 TTL=60s（key=user_id，缓存含 ws_container_id + backend_url）。WS-Master 内部触发 default ws-container 的 lazy start（见 [ws-master.md](./ws-master.md) §7.2）。
4. **proxy**：`httpx.AsyncClient` 反代到 `backend_url`，SSE 端点用 `client.stream("GET", ...)`。剔除 `Cookie` / `Authorization` / hop-by-hop 头；注入 `X-Everlingo-User: <user_id>`。

> 多 ws 演进：Phase 1 WS-Router 调 `default-ws/backend`（每 user 仅一个 ws-container，即 default）。未来放开多 ws 时，可改为先 `GET /internal/users/{user_id}/ws` 列出 ws-container 让用户选择，再 `GET /internal/ws/{ws_container_id}/backend` 解析。缓存 key 届时改为 `ws_container_id`。

### 3.4 AuthProvider 抽象（预留 SSO）

```python
class AuthProvider(Protocol):
    async def login(self, request) -> User: ...
    async def authenticate(self, request) -> User | None: ...
    def login_routes(self) -> APIRouter: ...
```

- `PasswordAuthProvider`（Phase 1）：用户名+口令，校验委派 WS-Master `/internal/authenticate`。
- `GoogleSSOAuthProvider`（Phase 2 预留）：OAuth2 Authorization Code + PKCE，回调换 id_token，按 `(provider, subject)` 查 `user_identities` 表解析 user_id，注入相同 JWT。仅新增一个 Provider 子类，WS-Router 主管线不变。

配置 `ws_router.auth.providers` 为列表，未来可同时启用 password + google_sso + github_sso 等多个 SSO provider。

> 认证数据分离：`PasswordAuthProvider` 查 WS-Master `users` 表（user_name + password_hash）；SSO provider 查 WS-Master `user_identities` 表（`(provider, subject)` → user_id）。`AuthProvider` 抽象在 WS-Router 侧统一登录入口，底层数据存储按凭证性质分离（见 [ws-master.md](./ws-master.md) §4.2）。

### 3.5 Google SSO 兼容路径（Phase 2）

方案 A（服务端渲染登录页）对 Google SSO 完全兼容，无需改架构：

1. 登录页加一个「Sign in with Google」按钮 → `GET /login/google`
2. WS-Router 走 OAuth2 Authorization Code + PKCE 流程：
   - 重定向到 Google 授权页（`scope=openid email profile`）
   - 用户授权后 Google 回调 `GET /login/google/callback?code=...`
   - WS-Router 用 code 换 id_token / access_token
   - 从 id_token 取 `sub` 作为 `subject`，连同 `provider="google"` → 调 WS-Master 查 `user_identities WHERE provider=? AND subject=?`（见 [ws-master.md](./ws-master.md) §4.2）
   - 命中 user → 取 `user_id` → 签发与密码登录**相同**的 JWT（HS256, sub=user_id）→ Set-Cookie + 302 `/`
   - 未命中 → 首次登录可自动建 user + 写入 `user_identities`（自助注册，从 id_token 取 email/display_name 生成 user_name/display_name），或拒绝并提示联系管理员
3. SSO 成功后签发的 JWT 与密码登录走同一条 `auth_middleware`，下游 backend 反代逻辑零改动。

**多 SSO provider 并存**：`user_identities` 表按 `(provider, subject)` 唯一约束，一个 user 可绑多个 provider（既 Google 又 GitHub）。绑定额外 provider：已登录用户发起另一 provider 的 OAuth，回调时若该 identity 未被其他 user 绑定，则挂到当前 user_id。WS-Router 按 `provider` 字段路由到对应 `AuthProvider` 子类，各 provider 独立配置 client_id/secret/redirect_uri。

**为什么方案 A 不阻碍 SSO**：
- 登录页是 WS-Router 服务端渲染，加按钮和 OAuth redirect 很简单，不需要前端构建
- 登录页 HTML 极简（一个 form + 少量 CSS），加按钮无负担
- `AuthProvider` Protocol 抽象让 password 与各 SSO provider 可并存

**Phase 2 待决策（不阻塞 Phase 1）**：
- 首次 SSO 登录是否自动建用户（自助注册）还是需要管理员预建
- 自动建用户时 `user_name` 生成规则（provider 上报的 email 前缀？顺序编号？）

Phase 1 只需保证 `AuthProvider` 抽象与 `user_identities` 表 schema 存在即可。

## 4. 路由

### 4.1 WS-Router 自有路由

| Method | Path | 说明 |
|---|---|---|
| GET / POST | `/login` | 登录页（HTML 表单）/ 提交凭证 |
| GET | `/logout` | 清 cookie，302 `/login` |
| GET | `/me` | 返回 `{user_id, user_name, display_name}` |
| GET | `/login/google` | （预留）重定向到 Google OAuth |
| GET | `/login/google/callback` | （预留）OAuth 回调 |

### 4.2 反代路由（透传到后端容器）

`/`、`/editor`、`/api/session/...`、`/api/session/{id}/events`（SSE）、`/manifest.webmanifest` 等全部透传。后端 ws-container 内的 `web_acceptor.py` 逻辑不变（见 [web-session-acceptor.md](../web-session-acceptor.md)）。

### 4.3 登录页（HTML）

WS-Router 镜像是精简构建（**无 `web/dist`**，见 [deploy.md](./deploy.md) §5.2），不能复用现有前端 SPA。主 SPA 由后端 ws-container 提供（`/` 反代过去）。因此登录页必须由 WS-Router 自己提供，采用**服务端渲染最小 HTML**（无前端构建依赖）。

- `GET /login` → 返回 HTML 登录表单（含 username/password 输入框、提交按钮）。HTML 模板可硬编码在 WS-Router 代码或 `src/everlingo/ws_router/templates/login.html`，极简 CSS。
- `POST /login` → 校验凭证：
  - 成功 → Set-Cookie + 302 `/`（浏览器跳到主 SPA）
  - 失败 → 返回表单 + 错误提示
- `GET /logout` → 清 cookie + 302 `/login`

**未认证访问的分流**（`auth_middleware`）：

| 客户端 | 判定 | 响应 |
|---|---|---|
| 浏览器 | `Accept: text/html` 且无凭证 | 302 `/login` |
| 程序化 | 带 `Authorization` 或 `Accept: application/json` | 401 JSON（`WWW-Authenticate: Bearer realm="everlingo"`） |

**Chrome Extension 登录**：Extension 不走登录页，而是通过 Extension Options 配置 Token 字段（PAT 或 access_token），或弹窗内放「登录」按钮调 WS-Router `POST /login` 拿 access_token 存起来。详见 PR4（Chrome Extension Token 化）。

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

Chrome Extension origin（`chrome-extension://<id>`）请求 WS-Router 属跨源。WS-Router 配置：

```python
CORSMiddleware(
    allow_origins=ws_router.cors_allow_origins,   # 扩展 ID 白名单（读 ws_router.yaml）
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=False,                # 不依赖 cookie 凭据
)
```

因程序化客户端用 `Authorization` 头而非 cookie，`allow_credentials=False` 即可。CORSMiddleware 自动处理 OPTIONS 预检。

## 5. 配置

`ws_router.yaml`：

```yaml
ws_router:
  listen: 0.0.0.0:8100
  base_url: https://app.everlingo.com
  trusted_proxy: 127.0.0.1          # 仅信任 nginx 来源

  master_url: http://ws_master:8101
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

`deploy/ws-router/Dockerfile`，单独精简构建（跳过 frontend-builder stage，无 `web/dist`）。详见 [deploy.md](./deploy.md) §镜像构建。

## 7. 关键不变量

- WS-Router 永远不直接读 `ws_master.sqlite`，也不调 docker daemon；user → backend 的解析与 ws-container 生命周期一律委派 WS-Master。
- WS-Router 可水平扩展多副本（共享 `jwt_secret` / `master_secret` 即可），无状态。
- TLS 永远不在 WS-Router 终止；cookie Secure 位依据 `X-Forwarded-Proto`。
