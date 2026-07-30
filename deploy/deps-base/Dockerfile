# EverLingo Python 依赖基础镜像
# 构建：
#   docker build -t ghcr.io/labilezhu/everlingo-deps:<ver> -f deploy/deps-base/Dockerfile .
#   或带 proxy:
#   docker build --build-arg HTTP_PROXY=... --build-arg HTTPS_PROXY=... -t ... .
#
# 下游 Dockerfile（ws-container/ws-master/ws-router）通过 `FROM` 此镜像，
# 源码改动只需 push src 层（KB 级），不再重下 ≈100M 的 .venv 层。

FROM python:3.12.13-bookworm AS deps

ARG HTTP_PROXY
ARG HTTPS_PROXY
ENV HTTP_PROXY=$HTTP_PROXY
ENV HTTPS_PROXY=$HTTPS_PROXY

RUN pip install --no-cache-dir "uv==0.12.0"
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
# 归零 mtime，确保同一 uv.lock 产出 byte-identical .venv → layer digest 稳定
RUN find /app/.venv -exec touch -h -d @0 {} +

FROM python:3.12.13-bookworm AS runtime

ARG HTTP_PROXY
ARG HTTPS_PROXY
ENV HTTP_PROXY=$HTTP_PROXY
ENV HTTPS_PROXY=$HTTPS_PROXY

RUN groupadd -g 1000 everlingo && \
    useradd -m -u 1000 -g 1000 -s /bin/bash everlingo && \
    apt-get update && apt-get install -y --no-install-recommends sudo && \
    echo "everlingo ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --chown=everlingo:everlingo --from=deps /app/.venv .venv/
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
