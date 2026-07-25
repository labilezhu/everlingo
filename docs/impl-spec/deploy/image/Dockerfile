# EverLingo 多阶段构建
# 构建命令（在 repo root 执行）：
#   docker build -t everlingo:v0.1 -f docs/impl-spec/deploy/image/Dockerfile .

# ── Stage 1: frontend-builder ────────────────────────────────────────────────
FROM node:20-bookworm-slim AS frontend-builder

ARG HTTP_PROXY
ARG HTTPS_PROXY

ENV HTTP_PROXY=$HTTP_PROXY
ENV HTTPS_PROXY=$HTTPS_PROXY

WORKDIR /web
COPY web/ ./
RUN npm ci && npm run build
# 产物: /web/dist（Web Chatbot + Vault Editor SPA）

# ── Stage 2: deps ────────────────────────────────────────────────────────────
FROM python:3.12.13-bookworm AS deps

ARG HTTP_PROXY
ARG HTTPS_PROXY

ENV HTTP_PROXY=$HTTP_PROXY
ENV HTTPS_PROXY=$HTTPS_PROXY

RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src/ src/
RUN uv sync --frozen --no-dev
RUN .venv/bin/python -m unidic download
# 产物: /app/.venv（含全部 Python 依赖 + unidic 词典数据）

# ── Stage 3: runtime ─────────────────────────────────────────────────────────
FROM python:3.12.13-bookworm AS runtime

ARG HTTP_PROXY
ARG HTTPS_PROXY

ENV HTTP_PROXY=$HTTP_PROXY
ENV HTTPS_PROXY=$HTTPS_PROXY

# everlingo 非 root 用户 + sudo
RUN groupadd -g 1000 everlingo && \
    useradd -m -u 1000 -g 1000 -s /bin/bash everlingo && \
    apt-get update && apt-get install -y --no-install-recommends sudo && \
    echo "everlingo ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app
# Python 依赖 + unidic 词典
COPY --from=deps /app/.venv .venv/
# 应用源码
COPY src/ src/
COPY pyproject.toml ./
# 前端 SPA 构建产物
COPY --from=frontend-builder /web/dist web/dist/
# workspace 模板 + entrypoint.sh（路径相对 repo root）
COPY docs/impl-spec/deploy/image/root/ /
# 调整所有权
RUN chown -R everlingo:everlingo /app /home/everlingo
USER everlingo
ENV PATH="/app/.venv/bin:$PATH" \
    EVERLINGO_WORKSPACE_DIR=/home/everlingo/.everlingo/workspaces/default
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
