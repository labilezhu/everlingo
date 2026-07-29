# EverLingo WS-Router 镜像（精简构建，跳过 frontend-builder，无 web/dist）
# 构建命令（在 repo root 执行）：
#   docker buildx build -f deploy/ws-router/Dockerfile -t everlingo-ws-router:0.1 .

# Stage: deps（与现有 Dockerfile 的 deps stage 一致）
FROM python:3.12.13-bookworm AS deps
RUN pip install uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Stage: runtime
FROM python:3.12.13-bookworm AS runtime
RUN useradd -m -u 1000 everlingo
COPY --chown=everlingo:everlingo --from=deps /app/.venv .venv/
COPY --chown=everlingo:everlingo src/ src/
COPY --chown=everlingo:everlingo pyproject.toml ./
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
USER everlingo
ENTRYPOINT ["python", "-m", "everlingo", "ws_router", "--config", "/etc/everlingo/ws_router.yaml"]
