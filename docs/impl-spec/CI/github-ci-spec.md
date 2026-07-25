# GitHub Actions CI 规范

本文档定义 EverLingo 通过 GitHub Actions 构建多架构（amd64 + arm64）Linux 容器镜像并发布到 GitHub Container Registry (GHCR) 的流程。镜像本身的构建逻辑、Dockerfile、entrypoint 等参见 [`../deploy/image/container-spec.md`](../deploy/image/container-spec.md)。

## 概述

- **触发方式**：推送 `v*` tag（正式发布 / prerelease）或 `workflow_dispatch` 手动触发
- **产物 Registry**：`ghcr.io/<owner>/everlingo`
- **认证**：使用 workflow 默认的 `GITHUB_TOKEN`，无需额外 secret
- **构建策略**：双 native runner 并行构建（amd64 / arm64 各自原生 runner，避免 QEMU 模拟），再以 manifest 合并为统一多架构镜像
- **缓存**：`type=gha`，按 arch 分 scope（`everlingo-amd64` / `everlingo-arm64`）

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

### 2. 手动触发（`workflow_dispatch`）

GitHub Actions 页面 → 选择 `docker-release` workflow → Run workflow。

可填 `tag_suffix` 可选输入，最终镜像 tag 为 `dev-<run_id>` 或 `dev-<run_id>-<suffix>`，**不**打 `latest`。用于调试 Dockerfile / 验证多架构构建，不影响正式 tag。

## 构建策略

| 平台 | Runner | 说明 |
|---|---|---|
| `linux/amd64` | `ubuntu-24.04` | GitHub 原生 x86_64 runner |
| `linux/arm64` | `ubuntu-24.04-arm` | GitHub 原生 arm64 runner（无需 QEMU 模拟） |

两个 build job 并行执行，各自完成 `docker buildx build --platform=linux/<arch> --push`，推到 GHCR 的 `<tag>-amd64` / `<tag>-arm64` 单架构 tag。

随后 `manifest` job 用 `docker buildx imagetools create` 将每对单架构 tag 合并为同名多架构 tag，使 `docker pull ghcr.io/<owner>/everlingo:<tag>` 自动按宿主架构拉取。

### 缓存

每平台独立 GHA cache：

- `cache-from: type=gha,scope=everlingo-amd64`
- `cache-to:   type=gha,mode=max,scope=everlingo-amd64`
- arm64 同理

`mode=max` 缓存多阶段所有 layer，二次构建命中后显著加速（尤其 `uv sync` + `unidic download` 的 deps stage）。

## Tag 规则

由 `docker/metadata-action@v5` 推导：

| 来源 | 生成 tag | 是否 `latest` |
|---|---|---|
| `v1.2.3` | `1.2.3` / `1.2` / `1` | ✅ |
| `v1.2.3-rc.1` | `1.2.3-rc.1` / `1.2.3` | ❌ |
| `workflow_dispatch` | `dev-<run_id>` 或 `dev-<run_id>-<suffix>` | ❌ |

`latest` 仅在稳定 semver tag（无 prerelease）时打，由 metadata-action 自动判断。

## GHCR 可见性配置

首次 workflow 推送后，GHCR 上的 `everlingo` package 默认继承仓库可见性（通常为 private）。如需公开供他人免登录拉取，需手动调整：

1. GitHub → 仓库 owner 的主页（个人或组织）→ **Packages** 标签
2. 点击 `everlingo` package
3. 右侧 **Package settings**
4. 拉到底部 **Danger Zone** → **Change visibility** → 选择 **Public**

### 拉取

- **Public package**：无需登录
  ```bash
  docker pull ghcr.io/<owner>/everlingo:0.1.0
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
3. GitHub Actions 自动触发 `docker-release` workflow
4. 两个 build job 并行执行（约 5–10 分钟 / 平台，首次较慢，命中 cache 后更快）
5. `manifest` job 合并多架构 tag（约 1 分钟）
6. 拉取使用：
   ```bash
   docker pull ghcr.io/<owner>/everlingo:0.1.0
   docker run -d -p 8000:8000 \
     -v ~/everlingo_workspaces/mark:/home/everlingo/.everlingo/workspaces/default \
     ghcr.io/<owner>/everlingo:0.1.0
   ```

部署细节（workspace 挂载、配置模板等）参见 [`container-spec.md`](../deploy/image/container-spec.md) 的「经典部署方法」节。

## 本地构建

CI 仅负责发布。本地开发构建仍按 [`container-spec.md`](../deploy/image/container-spec.md) 的「Run build image」节执行：

```bash
cd $everlingo_repo
DOCKER_BUILDKIT=1 docker buildx build . -f docs/impl-spec/deploy/image/Dockerfile
```

## 相关文档

- [Image 设计规范](../deploy/image/container-spec.md)
- [产品文档](../../PRODUCT-FUNC.md)
