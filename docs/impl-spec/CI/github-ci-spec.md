# GitHub Actions CI 规范

本文档定义 EverLingo 通过 GitHub Actions 构建多架构（amd64 + arm64）Linux 容器镜像并发布到 GitHub Container Registry (GHCR) 的流程。涵盖三组镜像：

| Package | Dockerfile | 用途 | 说明 |
|---|---|---|---|
| `everlingo` | `deploy/ws-container/Dockerfile` | workspace container（单用户独立部署或用 WS-Master 动态创建） | 多阶段构建，含 `web/dist` 前端 SPA |
| `everlingo-ws-master` | `deploy/ws-master/Dockerfile` | 多用户编排服务 | 精简构建，跳过 frontend-builder，无 `web/dist` |
| `everlingo-ws-router` | `deploy/ws-router/Dockerfile` | 多用户路由入口 | 精简构建，同 ws-master |

每镜像的 Dockerfile 设计、entrypoint、进程编排等参见 [`../../deploy/ws-container/ws-container-spec.md`](../../deploy/ws-container/ws-container-spec.md)、[`../../docs/impl-spec/multiple-users/ws-master.md`](../../docs/impl-spec/multiple-users/ws-master.md)、[`../../docs/impl-spec/multiple-users/ws-router.md`](../../docs/impl-spec/multiple-users/ws-router.md)。

## 概述

- **触发方式**：推送 `v*` tag（正式发布 / prerelease）或 `workflow_dispatch` 手动触发
- **产物 Registry**：`ghcr.io/<owner>/everlingo`、`ghcr.io/<owner>/everlingo-ws-master`、`ghcr.io/<owner>/everlingo-ws-router`
- **认证**：使用 workflow 默认的 `GITHUB_TOKEN`，无需额外 secret
- **构建策略**：双 native runner 并行构建（amd64 / arm64 各自原生 runner，避免 QEMU 模拟），再以 manifest 合并为统一多架构镜像。三组镜像在一次触发中并行构建，互不阻塞。
- **缓存**：`type=gha`，按镜像 × arch 分 scope

## Workflow 文件

`.github/workflows/docker-release.yml`

## 触发条件

### 1. Tag 触发（正式发布）

推 `v*` 格式的 git tag 即触发，例如：

```bash
git tag v0.1.0
git push origin v0.1.0
```

支持 SemVer：

| Git tag | 产物 tag |
|---|---|
| `v1.2.3` | `1.2.3` + `1.2` + `1` + `latest` |
| `v1.2.3-rc.1` | `1.2.3-rc.1` + `1.2.3`（**不**打 `latest`，避免用户误拉不稳定版本） |

三组镜像各自独立应用此规则，互不影响。

### 2. 手动触发（`workflow_dispatch`）

GitHub Actions 页面 → 选择 `docker-release` workflow → Run workflow。

可填 `tag_suffix` 可选输入，最终镜像 tag 为 `dev-<run_id>` 或 `dev-<run_id>-<suffix>`，**不**打 `latest`。三组镜像同时以该 tag 发布。

## 构建策略

| 平台 | Runner | 说明 |
|---|---|---|
| `linux/amd64` | `ubuntu-24.04` | GitHub 原生 x86_64 runner |
| `linux/arm64` | `ubuntu-24.04-arm` | GitHub 原生 arm64 runner（无需 QEMU 模拟） |

`build` job 以 matrix 枚举 6 个组合（3 image × 2 arch），各自并行执行 `docker buildx build --platform=linux/<arch> --push`，推到 GHCR 的 `<tag>-<arch>` 单架构 tag。

`manifest` job 以 matrix 枚举 3 个 image，对每镜像用 `docker buildx imagetools create` 将对应 amd64 + arm64 单架构 tag 合并为同名多架构 tag，使 `docker pull ghcr.io/<owner>/everlingo:<tag>` 自动按宿主架构拉取。

### 构建矩阵

```
image            | dockerfile                    | arch   | runner
─────────────────|───────────────────────────────|────────|────────────────
everlingo        | deploy/ws-container/Dockerfile | amd64  | ubuntu-24.04
everlingo        | deploy/ws-container/Dockerfile | arm64  | ubuntu-24.04-arm
everlingo-ws-master | deploy/ws-master/Dockerfile | amd64  | ubuntu-24.04
everlingo-ws-master | deploy/ws-master/Dockerfile | arm64  | ubuntu-24.04-arm
everlingo-ws-router | deploy/ws-router/Dockerfile | amd64  | ubuntu-24.04
everlingo-ws-router | deploy/ws-router/Dockerfile | arm64  | ubuntu-24.04-arm
```

### 缓存

每镜像每平台独立 GHA cache：

| cache scope | 对应构建 |
|---|---|
| `everlingo-amd64` | everlingo × amd64 |
| `everlingo-arm64` | everlingo × arm64 |
| `everlingo-ws-master-amd64` | everlingo-ws-master × amd64 |
| `everlingo-ws-master-arm64` | everlingo-ws-master × arm64 |
| `everlingo-ws-router-amd64` | everlingo-ws-router × amd64 |
| `everlingo-ws-router-arm64` | everlingo-ws-router × arm64 |

`mode=max` 缓存多阶段所有 layer，二次构建命中后显著加速（尤其 `uv sync` 的 deps stage）。三组镜像的 deps stage 内容相同，但 cache scope 分离，可并行读写互不冲突。

## Tag 规则

由 `docker/metadata-action@v5` 推导：

| 来源 | 生成 tag | 是否 `latest` |
|---|---|---|
| `v1.2.3` | `1.2.3` / `1.2` / `1` | ✅ |
| `v1.2.3-rc.1` | `1.2.3-rc.1` / `1.2.3` | ❌ |
| `workflow_dispatch` | `dev-<run_id>` 或 `dev-<run_id>-<suffix>` | ❌ |

`latest` 仅在稳定 semver tag（无 prerelease）时打，由 metadata-action 自动判断。三组镜像各自拥有独立 `latest` tag（如 `everlingo-ws-master:latest`），互不干扰。

## GHCR 可见性配置

首次 workflow 推送后，GHCR 上会出现三个 package（`everlingo`、`everlingo-ws-master`、`everlingo-ws-router`），默认继承仓库可见性（通常为 private）。如需公开供他人免登录拉取，需对每个 package 分别调整：

1. GitHub → 仓库 owner 的主页（个人或组织）→ **Packages** 标签
2. 点击对应 package
3. 右侧 **Package settings**
4. 拉到底部 **Danger Zone** → **Change visibility** → 选择 **Public**

### 拉取

- **Public package**：无需登录
  ```bash
  docker pull ghcr.io/<owner>/everlingo:0.1.0
  docker pull ghcr.io/<owner>/everlingo-ws-master:0.1.0
  docker pull ghcr.io/<owner>/everlingo-ws-router:0.1.0
  ```
- **Private package**：需 PAT（`read:packages` scope）
  ```bash
  echo $PAT | docker login ghcr.io -u <username> --password-stdin
  docker pull ghcr.io/<owner>/everlingo:0.1.0
  ```

## 仓库权限要求

workflow 顶部声明：

```yaml
permissions:
  contents: read
  packages: write
```

仓库层面需确保：**Settings → Actions → General → Workflow permissions** 设为 **"Read and write permissions"**，否则 `packages: write` 不生效，推送会 403。

## 发布流程

1. 改代码、更新版本号、commit
2. 打 tag 并推送：
   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```
   或 RC:
   ```bash
   git tag v0.0.1-rc.1
   git push origin v0.0.1-rc.1
   ```

3. GitHub Actions 自动触发 `docker-release` workflow
4. 6 个 build job 并行执行（每个平台约 5–10 分钟，首次较慢，命中 cache 后更快）
5. 3 个 manifest job 各自合并多架构 tag（约 1 分钟）
6. 拉取使用：
   ```bash
   docker pull ghcr.io/<owner>/everlingo:0.1.0
   docker pull ghcr.io/<owner>/everlingo-ws-master:0.1.0
   docker pull ghcr.io/<owner>/everlingo-ws-router:0.1.0
   ```

单用户独立部署参见 [`ws-container-spec.md`](../../deploy/ws-container/ws-container-spec.md) 的「经典部署方法」节；多用户编排部署参见 [`../../docs/impl-spec/multiple-users/deploy.md`](../../docs/impl-spec/multiple-users/deploy.md)。

## 本地构建

CI 仅负责发布。本地开发构建仍按相应设计文档执行：

```bash
cd $everlingo_repo

# workspace container（含前端）
DOCKER_BUILDKIT=1 docker buildx build . -f deploy/ws-container/Dockerfile -t everlingo:dev

# ws-master（无前端）
DOCKER_BUILDKIT=1 docker buildx build . -f deploy/ws-master/Dockerfile -t everlingo-ws-master:dev

# ws-router（无前端）
DOCKER_BUILDKIT=1 docker buildx build . -f deploy/ws-router/Dockerfile -t everlingo-ws-router:dev
```

代理环境下加 `--build-arg HTTP_PROXY=... --build-arg HTTPS_PROXY=...`。

## 相关文档

- [Image 设计规范](../../deploy/ws-container/ws-container-spec.md)
- [多用户部署编排](../../docs/impl-spec/multiple-users/deploy.md)
- [WS-Master 服务](../../docs/impl-spec/multiple-users/ws-master.md)
- [WS-Router 服务](../../docs/impl-spec/multiple-users/ws-router.md)
- [产品文档](../../PRODUCT-FUNC.md)
