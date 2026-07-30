# EverLingo WS-Router 镜像（精简构建，跳过 frontend-builder，无 web/dist）
# 构建命令（在 repo root 执行）：
#   docker buildx build -f deploy/ws-router/Dockerfile -t everlingo-ws-router:0.1 .

# Stage: runtime
ARG DEPS_IMAGE=ghcr.io/labilezhu/everlingo-deps:latest
FROM ${DEPS_IMAGE} AS runtime
WORKDIR /app
COPY --chown=everlingo:everlingo src/ src/
COPY --chown=everlingo:everlingo pyproject.toml ./
USER everlingo
# ENTRYPOINT 仅固定基础调用，子命令与 --config 由 compose command: 提供
ENTRYPOINT ["python", "-m", "everlingo"]
