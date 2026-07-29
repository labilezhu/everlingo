# Internal API 契约（WS-Master ↔ WS-Router）

- 状态：Planned（2026-07-29）
- 相关文档：
  - [ws-master.md](./ws-master.md) — WS-Master 服务说明（§6 概览）
  - [ws-router.md](./ws-router.md) — WS-Router 服务说明（§3.3 调用方）
- 定位：本文件是 WS-Master（实现方）与 WS-Router（消费方）之间的**稳定 API 契约**，
  PR1 与 PR2 共同依据。契约变更须双方向本文件提 PR 同步，不得单边改实现。

---

## 1. 通用约定

### 1.1 传输

- 基础 URL：`http://ws_master:8101`（`everlingo-net` 内，不对外）
- 所有请求**必须**带头 `X-Master-Token: <shared_secret>`（与 `ws_master.yaml.master.shared_secret`
  / `ws_router.yaml.ws_router.master_secret` 一致）。缺失或不符 → `401`。
- 请求/响应 body 均为 `application/json`（`GET /internal/healthz` 例外，可为纯文本）。
- 字符编码 UTF-8。

### 1.2 标识与时间

| 字段类型 | 格式 |
|---|---|
| `user_id` / `ws_container_id` / `pat id` / `identity_id` | UUID v4 字符串（小写，带连字符） |
| 所有时间字段 | ISO8601 UTC，如 `2026-07-29T12:00:00Z` |

### 1.3 错误响应

统一结构化格式：

```json
{
  "error": {
    "code": "<machine_code>",
    "message": "<human readable>",
    "details": { }
  }
}
```

- `code`：snake_case 机读码，WS-Router 据此区分处理（见各端点的「错误码」）。
- `message`：可读描述，可用于日志/调试，**不**直接展示给最终用户。
- `details`：可选，端点特定补充信息（如 `{"status": "starting"}`）。

通用错误码（所有端点都可能返回）：

| HTTP | code | 含义 |
|---|---|---|
| 401 | `unauthorized` | 缺失/错误 `X-Master-Token` |
| 404 | `not_found` | 路径参数对应的资源不存在（端点可覆写为更具体的 code，如 `user_not_found`） |
| 500 | `internal_error` | 未预期异常（details 可空，避免泄露内部栈） |

### 1.4 幂等与并发

- 读端点（GET）幂等。
- `POST /internal/authenticate` / `/internal/pat/verify` 幂等（相同输入相同结果，verify 额外回写
  `last_used_at`）。
- `POST /internal/pat` 非幂等（每次生成新 token）。
- `POST /internal/ws/{id}/ensure_started` 幂等（已 started 则探活后返回 URL）。

---

## 2. 端点契约

### 2.1 `POST /internal/authenticate`

校验用户名+口令（`PasswordAuthProvider` 委派调用）。

**请求**
```json
{ "username": "mark", "password": "secret" }
```

**成功** `200`
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_name": "mark",
  "display_name": "Mark"
}
```

**错误**

| HTTP | code | 含义 |
|---|---|---|
| 401 | `invalid_credentials` | 用户名不存在**或**口令错误（统一 401，防用户名枚举） |

> 故意不区分 `user_not_found` 与 `wrong_password`，避免用户名枚举攻击。

---

### 2.2 `POST /internal/pat/verify`

校验 PAT 明文。命中则回写 `pat_tokens.last_used_at`。

**请求**
```json
{ "token": "elpat_..." }
```

**成功** `200`
```json
{
  "user_id": "...",
  "user_name": "mark",
  "display_name": "Mark"
}
```

**错误**

| HTTP | code | 含义 |
|---|---|---|
| 401 | `invalid_token` | token 不存在 / 已过期 / 已吊销（统一对外，不暴露具体原因） |

> 成功响应字段与 `authenticate` 对齐，便于 WS-Router 两条认证路径下游处理一致。

---

### 2.3 `POST /internal/pat`

生成 PAT。明文 token 仅本次响应返回，WS-Master 以 sha256 哈希存储。

> **Phase 1**：实现本端点，但 WS-Router 不调用（PAT 经 WS-Master CLI 生成，见
> [ws-master.md](./ws-master.md) §8）。保留此端点供未来「Web UI 生成 PAT」使用。

**请求**
```json
{
  "user_id": "550e8400-...",
  "label": "curl-laptop",
  "expires_at": "2027-07-29T00:00:00Z"
}
```
- `label` 必填，人类可读标签。
- `expires_at` 可选，NULL = 永久。

**成功** `201`
```json
{
  "id": "660e8400-...",
  "token": "elpat_<随机>",
  "user_id": "550e8400-...",
  "label": "curl-laptop",
  "created_at": "2026-07-29T12:00:00Z",
  "expires_at": "2027-07-29T00:00:00Z"
}
```

**错误**

| HTTP | code | 含义 |
|---|---|---|
| 404 | `user_not_found` | `user_id` 不存在 |
| 400 | `invalid_request` | 缺失必填字段 / `expires_at` 格式错误 / 已过期时间 |

---

### 2.4 `GET /internal/users/{user_id}`

查用户基本信息。WS-Router `/me` 端点用此获取（可改的）`display_name`。

**成功** `200`
```json
{
  "user_id": "...",
  "user_name": "mark",
  "display_name": "Mark",
  "created_at": "2026-07-28T10:00:00Z"
}
```

**错误**

| HTTP | code | 含义 |
|---|---|---|
| 404 | `user_not_found` | |

---

### 2.5 `GET /internal/users/{user_id}/ws`

列出该 user 的所有 ws-container。未来放开多 ws 时 WS-Router 用于让用户选择 ws。

**成功** `200`
```json
[
  {
    "ws_container_id": "770e8400-...",
    "status": "started",
    "is_default": true,
    "container_name": "everlingo-mark-a1b2c3d4"
  }
]
```
- `status`：`absent` / `creating` / `starting` / `started` / `stopped` / `error`（见
  [ws-master.md](./ws-master.md) §7）。
- 空列表 `[]` 表示该 user 存在但无 ws-container（Phase 1 不应发生：`user add` 同步创建 default ws）。

**错误**

| HTTP | code | 含义 |
|---|---|---|
| 404 | `user_not_found` | |

---

### 2.6 `GET /internal/users/{user_id}/default-ws/backend`

解析 default ws-container 并 lazy start。**Phase 1 WS-Router 实际使用的便捷端点。**

**成功** `200`
```json
{
  "ws_container_id": "770e8400-...",
  "backend_url": "http://everlingo-mark-a1b2c3d4:8000",
  "status": "started"
}
```

**语义**（见 [ws-master.md](./ws-master.md) §6.1）：
1. 查 `ws_containers` 中 `user_id` 且 `is_default=1` 的行
2. `started` 且探活成功 → 返回 URL
3. `stopped` → `docker start` → 探活 → 返回 URL
4. `absent` → `docker create` + `start` → 探活 → 返回 URL
5. 正在 `creating`/`starting` → **复用 in-flight 结果**，最多等待 `readiness_timeout` 秒
6. 探活超 `readiness_timeout` → `503 backend_unavailable`

**错误**

| HTTP | code | details | 含义 |
|---|---|---|---|
| 404 | `user_not_found` | — | |
| 404 | `no_default_ws` | — | 该 user 无 default ws-container（Phase 1 不应发生） |
| 503 | `backend_unavailable` | `{"status": "error"\|"creating"\|"starting"}` | 启动失败或探活超时 |

> `503` 时 `details.status` 帮助 WS-Router 决策：`starting`/`creating` 可短退避重试，
> `error` 应返回错误页/提示。

---

### 2.7 `GET /internal/ws/{ws_container_id}/backend`

按 ws_container_id 解析（lazy start）。未来多 ws 时 WS-Router 选定 ws 后调用。语义与 §2.6 相同，
仅查询维度不同（按 ws_container_id 而非 user_id+default）。

**成功** `200`：同 §2.6。

**错误**

| HTTP | code | details | 含义 |
|---|---|---|---|
| 404 | `ws_not_found` | — | ws_container_id 不存在 |
| 503 | `backend_unavailable` | `{"status": "..."}` | 同 §2.6 |

---

### 2.8 `POST /internal/ws/{ws_container_id}/ensure_started`

强制拉起（即使 status=started 也重新探活）。用于 WS-Router 检测到后端异常时主动触发恢复。

**成功** `200`
```json
{
  "ws_container_id": "...",
  "backend_url": "http://everlingo-mark-a1b2c3d4:8000",
  "status": "started"
}
```

**错误**

| HTTP | code | details | 含义 |
|---|---|---|---|
| 404 | `ws_not_found` | — | |
| 503 | `backend_unavailable` | `{"status": "..."}` | 同 §2.6 |

---

### 2.9 `GET /internal/healthz`

WS-Master 自检（进程存活 + sqlite 可读）。

**成功** `200`
```json
{ "status": "ok" }
```

**错误**

| HTTP | code | 含义 |
|---|---|---|
| 503 | `unhealthy` | sqlite 不可读或内部状态异常 |

---

## 3. 字段词典

### 3.1 `status`（ws-container 生命周期状态）

取自 [ws-master.md](./ws-master.md) §7：

| 值 | 含义 |
|---|---|
| `absent` | 未创建 docker 容器（仅 DB 记录） |
| `creating` | 正在 `docker create` |
| `starting` | 已 `docker start`，探活未通过 |
| `started` | 运行中且探活通过 |
| `stopped` | 已 `docker stop`（容器对象仍在，可 start） |
| `error` | create/start 失败或探活超时（`error_message` 有值） |

### 3.2 token 格式

PAT 明文格式：`elpat_<base62 随机串>`（前缀便于辨识，避免与 JWT 混淆）。

---

## 4. 变更与版本

- 契约变更须双方向本文件提 PR 同步。
- 破坏性变更（删端点 / 改字段语义）需双方同时发版；Phase 1 阶段不设版本号，靠 PR 协调。
- 新增可选字段为兼容变更，不阻塞单方合入。

## 5. Phase 边界

| 端点 | Phase 1 | Phase 2+ |
|---|---|---|
| `authenticate` | ✅ 实现 + 使用 | 同 |
| `pat/verify` | ✅ 实现 + 使用 | 同 |
| `pat` (POST 生成) | ✅ 实现，**不**被 ws-router 调用 | Web UI 调用 |
| `users/{id}` | ✅ 实现 + 使用（`/me`） | 同 |
| `users/{id}/ws` | ✅ 实现，**不**被 ws-router 调用 | ws-router 用于多 ws 选择 |
| `users/{id}/default-ws/backend` | ✅ 实现 + 使用 | 同 |
| `ws/{id}/backend` | ✅ 实现，**不**被 ws-router 调用 | ws-router 用于多 ws |
| `ws/{id}/ensure_started` | ✅ 实现，**不**被 ws-router 调用 | ws-router 主动恢复用 |
| `healthz` | ✅ 实现 + 使用（compose healthcheck） | 同 |
| SSO 相关（identity 查/写） | ❌ 不实现（schema 已预留） | OAuth 回调写入 `user_identities` |

> Phase 1 实现"不调用"的端点：为保持 API 形状完整、避免 Phase 2 breaking change，PR1
> 一并实现并加单测，但 WS-Router 不接入。
