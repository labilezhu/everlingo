# EverLingo 多阶段构建
# 构建命令（在 repo root 执行）：
#   docker build -t everlingo:v0.1 -f deploy/ws-container/Dockerfile .
#   （先构建 deps-base 并传 --build-arg DEPS_IMAGE=everlingo-deps:local）

ARG DEPS_IMAGE=ghcr.io/labilezhu/everlingo-deps:latest

# ── Stage 1: frontend-builder ────────────────────────────────────────────────
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
# 产物: /web/dist（Web Chatbot + Vault Editor SPA）

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM ${DEPS_IMAGE} AS runtime
WORKDIR /app
COPY --chown=everlingo:everlingo src/ src/
COPY --chown=everlingo:everlingo pyproject.toml ./
# 前端 SPA 构建产物
COPY --chown=everlingo:everlingo --from=frontend-builder /web/dist web/dist/
# workspace 模板 + entrypoint.sh（路径相对 repo root）
COPY --chown=everlingo:everlingo deploy/ws-container/root/ /
USER everlingo
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    EVERLINGO_WORKSPACE_DIR=/home/everlingo/.everlingo/workspaces/default
EXPOSE 8000
# gateway /healthz 端点探活：见 ws-container-spec.md「image 进程健康检查（healthz）」
# start-period=60s 覆盖 indexer 冷启（加载 unidic-lite 词典 + sqlite 初始化）
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).read()" || exit 1
ENTRYPOINT ["/app/entrypoint.sh"]
