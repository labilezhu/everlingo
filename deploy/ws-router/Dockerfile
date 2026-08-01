# EverLingo WS-Router 镜像
# 构建命令（在 repo root 执行）：
#   docker buildx build -f deploy/ws-router/Dockerfile -t everlingo-ws-router:0.1 .

# ── Stage 1: frontend-builder ────────────────────────────────────────────────
# 构建 web/ 前端（含登录页 SPA 与公开静态资源）。产物 web/dist 供 WS-Router
# 本地服务 /login、/assets/*、/favicon.png、/manifest.webmanifest、/icon-*.png。
FROM node:20-bookworm-slim AS frontend-builder

ARG HTTP_PROXY
ARG HTTPS_PROXY

ENV HTTP_PROXY=$HTTP_PROXY
ENV HTTPS_PROXY=$HTTPS_PROXY

WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
ARG DEPS_IMAGE=ghcr.io/labilezhu/everlingo-deps:latest
FROM ${DEPS_IMAGE} AS runtime
WORKDIR /app
COPY --chown=everlingo:everlingo src/ src/
COPY --chown=everlingo:everlingo pyproject.toml ./
COPY --chown=everlingo:everlingo --from=frontend-builder /web/dist web/dist/
USER everlingo
# ENTRYPOINT 仅固定基础调用，子命令与 --config 由 compose command: 提供
ENTRYPOINT ["python", "-m", "everlingo"]
