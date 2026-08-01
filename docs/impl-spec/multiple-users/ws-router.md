# WS-Router Service

- 状态：Done（2026-07-29 修订）
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
- 登录页是 WS-Router 提供的 React SPA（见 §4.3），加「Sign in with Google」按钮 + `GET /login/google` 跳转很简单，不需要改 OAuth 流程
- `AuthProvider` Protocol 抽象让 password 与各 SSO provider 可并存

**Phase 2 待决策（不阻塞 Phase 1）**：
- 首次 SSO 登录是否自动建用户（自助注册）还是需要管理员预建
- 自动建用户时 `user_name` 生成规则（provider 上报的 email 前缀？顺序编号？）

Phase 1 只需保证 `AuthProvider` 抽象与 `user_identities` 表 schema 存在即可。

## 4. 路由

### 4.1 WS-Router 自有路由

| Method | Path | 说明 |
|---|---|---|
| GET / POST | `/login` | 登录页（React SPA）/ 提交凭证（JSON） |
| GET | `/logout` | 清 cookie，302 `/login` |
| GET | `/me` | 返回 `{user_id, user_name, display_name}` |
| GET | `/self-service` | 用户认证自服务页（React SPA，需登录） |
| GET | `/self-service/pat` | 永久 Token（浏览器扩展用）页（React SPA，需登录） |
| GET | `/self-service/api/pats` | 列出当前用户 PAT（JSON，需登录） |
| POST | `/self-service/api/pats` | 生成新 PAT，入参 `{label}` → `{id, token(明文仅一次), label, created_at, expires_at}`（需登录） |
| GET | `/login/google` | （预留）重定向到 Google OAuth |
| GET | `/login/google/callback` | （预留）OAuth 回调 |
| GET | `/assets/{path:path}` | 前端静态资源（登录页 + 公开 chunk） |
| GET | `/favicon.png` `/manifest.webmanifest` `/icon-*.png` | 前端公开静态文件（pre-auth 可达） |

### 4.2 反代路由（透传到后端容器）

`/`、`/editor`、`/api/session/...`、`/api/session/{id}/events`（SSE）、`/manifest.webmanifest` 等全部透传。后端 ws-container 内的 `web_acceptor.py` 逻辑不变（见 [web-session-acceptor.md](../web-session-acceptor.md)）。

### 4.3 登录页（React SPA）

登录页是 WS-Router 自己提供的 **React SPA**，由 `web/` Vite 项目构建（复用主 SPA 同一套前端技术栈，见 [web-chatbot.md](../web-chatbot.md) §前端技术选型：Vite + React + TailwindCSS + shadcn/ui）。

- 前端代码：`web/login.html`（Vite 入口）+ `web/src/login/`（`main.tsx`、`LoginPage.tsx`），`LoginPage.tsx` 使用 shadcn/ui 的 `Button` / `Input` 组件。
- `GET /login` → WS-Router 返回 `web/dist/login.html`（本地 `FileResponse`）；未构建时返回 503 JSON 提示。
- 登录表单提交走 `fetch('/login', ...)`（JSON + `Accept: application/json`），成功 200 → `window.location.href = '/'`，失败 401 → 行内显示错误。
- 登录页 `<head>` 带完整 PWA meta（manifest / apple-touch-icon / theme-color，与主 SPA 入口一致）。

#### 前端技术选型（登录页）

与 [web-chatbot.md](../web-chatbot.md) §前端技术选型 一致，复用 `web/` 项目：

| 层 | 选型 | 用途 |
|---|---|---|
| 构建 | Vite | `web/` 多入口构建（含 `login` 入口），产出 `web/dist` |
| UI 框架 | React | 登录表单状态、提交逻辑、错误展示 |
| 样式 | TailwindCSS | 布局 / 卡片 / 间距 / 响应式 |
| 组件库 | shadcn/ui | `Button`、`Input` |

不直接以 Python 字符串生成 HTML；登录页与主 SPA 共用同一 `web/` 工程与 `web/dist` 构建产物。

#### WS-Router 本地服务的公开静态资源

登录页在 **pre-auth** 阶段加载，其静态资源不能反代到 ws-container（pre-auth 无 `user_id`，无法 `backend_resolve`）。因此 WS-Router 本地服务以下公开静态资源（`auth_middleware` 白名单放行，均为公开静态代码/文件，无安全风险）：

| 路径 | 来源 | 说明 |
|---|---|---|
| `/assets/{path:path}` | `web/dist/assets/` | 登录页 JS/CSS chunk（Vite 共享 vendor chunk 无法按入口拆分，整目录服务；主 SPA 的同名 chunk 也由此服务） |
| `/favicon.png` | `web/dist/favicon.png` | 登录页 favicon |
| `/manifest.webmanifest` | `web/dist/manifest.webmanifest` | PWA manifest（登录页引用，pre-auth 可达） |
| `/icon-192.png` `/icon-512.png` `/icon-512-maskable.png` | `web/dist/...` | PWA 图标 |

主 SPA 的 HTML 入口（`/`、`/editor`、`/console/*`）仍由 ws-container 反代提供（post-auth），其静态资源请求会落到 WS-Router 本地 `/assets/*`——因两镜像共用同一 `web/dist`（CI 同步构建），asset hash 一致，行为正确。

**ws-container 职责不变**：单用户独立部署（无 WS-Router）时，ws-container 的 `web_acceptor.py` 依旧独自提供全部前端文件（含 PWA manifest / icons / favicon），见 [web-session-acceptor.md](../web-session-acceptor.md)。

**为什么 WS-Router 也提供 manifest / icons**：手机浏览器在加载**任何**带 `<link rel="manifest">` 的页面时都会读取 manifest（与登录状态无关）。iOS Safari「添加到主屏幕」是用户在任意页面手动触发的。若登录页不提供 manifest / apple-touch-icon，用户在登录页触发安装时图标会降级为截图或默认图标，体验差。因此登录页 `login.html` 引用与主 SPA 相同的 manifest / icons，WS-Router pre-auth 本地服务之。

**`POST /login` 仅支持 JSON 提交**（随服务端渲染 HTML 的移除，form 提交一并废弃）。程序化客户端（curl / Chrome Extension）与浏览器 React SPA 均走 JSON（见 §4.4）。

**未认证访问的分流**（`auth_middleware`）：

| 客户端 | 判定 | 响应 |
|---|---|---|
| 浏览器 | `Accept: text/html` 且无凭证 | 302 `/login` |
| 程序化 | 带 `Authorization` 或 `Accept: application/json` | 401 JSON（`WWW-Authenticate: Bearer realm="everlingo"`） |

**Chrome Extension 登录**：Extension 不走登录页，而是通过 Extension Options 配置 Token 字段（PAT 或 access_token），或弹窗内放「登录」按钮调 WS-Router `POST /login` 拿 access_token 存起来。详见 PR4（Chrome Extension Token 化）。

### 4.4 登录 API 响应

`POST /login` 仅支持 JSON 提交（登录页为 React SPA，浏览器经 `fetch` 提交；Chrome Extension / curl 亦为 JSON）：

```
POST /login
  Content-Type: application/json
  {"username": "...", "password": "..."}

成功 → 200 {
    "user_id": "...",
    "access_token": "<jwt>",
    "token_type": "bearer",
    "expires_at": "2026-07-28T20:00:00Z"
  }
  Set-Cookie: everlingo_sess=<jwt>; HttpOnly; Secure; SameSite=Lax

失败 → 401 {
    "error": { "code": "invalid_credentials", "message": "Invalid username or password" }
  }
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

### 4.6 用户认证自服务页（self-service）

WS-Router 提供两个认证自服务 SPA 页面（React SPA，与登录页同属 `web/` Vite 项目，独立 entry），**post-auth** 访问（不在 auth_middleware 白名单，未认证浏览器 302 `/login`，程序化客户端 401）：

- `GET /self-service` → `web/dist/self-service.html`：header 后退按钮 + 「永久 Token」入口卡片 + 底部「退出登录」按钮（`GET /logout`）。
- `GET /self-service/pat` → `web/dist/pat.html`：header 后退按钮 + 生成表单（仅 `label`）+ 明文 token 展示（仅一次 + 复制按钮）+ 当前用户 PAT 列表。

PAT 数据经 WS-Router 后端调 WS-Master internal API（`MasterClient.pat_list` / `pat_create`），不透传 ws-container；`request.state.user_id` 来自 auth_middleware 验签结果。明文 token 仅创建响应返回一次。

路由注册在 catch-all（反代）之前，避免被透传到后端 ws-container。前端后退按钮用 `history.back()`，无历史时回退 `/` 或 `/self-service`。

## 5. 配置

`ws_router.yaml` 所有字符串字段默认支持 `os.path.expandvars` 环境变量展开（`${VAR}` / `$VAR` 嵌入式均可），
未设 env 时保留原字面量（fail-loud）。典型用例：`master_secret: ${MASTER_SECRET}`。

```yaml
ws_router:
  listen: 0.0.0.0:8100
  public_base_url: https://app.everlingo.com   # 外部访问地址；应与 ws_master.yaml 的 public_base_url 保持一致
  trusted_proxy: 127.0.0.1          # 仅信任 nginx 来源

  master_url: http://ws_master:8101
  master_secret: ${MASTER_SECRET}   # 与 master.shared_secret 一致，注入 X-Master-Token
  master_timeout: 90                # 调用 master Internal API 的 HTTP 超时（秒）
                                    # 必须 >= ws_master 的 readiness_timeout + buffer
                                    # 否则 router 会在 master 仍在等就绪时先超时 → 503 假错误

  jwt_secret: ${JWT_SECRET}         # HS256 签名密钥
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

`deploy/ws-router/Dockerfile`，含 frontend-builder stage（构建 `web/` 前端 → `web/dist`），runtime 携带 `web/dist` 用于本地服务登录页、认证自服务页（`/self-service`、`/self-service/pat`）与公开静态资源（见 §4.3 / §4.6）。其余依赖与 WS-Master 相同（`src/`、`pyproject.toml`）。详见 [deploy.md](./deploy.md) §5.2。

## 7. 关键不变量

- WS-Router 永远不直接读 `ws_master.sqlite`，也不调 docker daemon；user → backend 的解析与 ws-container 生命周期一律委派 WS-Master。
- WS-Router 可水平扩展多副本（共享 `jwt_secret` / `master_secret` 即可），无状态。
- TLS 永远不在 WS-Router 终止；cookie Secure 位依据 `X-Forwarded-Proto`。
