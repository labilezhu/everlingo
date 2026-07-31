#!/usr/bin/env bash
set -euo pipefail

WS="${EVERLINGO_WORKSPACE_DIR:-/home/everlingo/.everlingo/workspaces/default}"
MCP_URL_FILE="$WS/indexer.mcp.url"
rm -f "$MCP_URL_FILE"  # 清理上一轮容器残留（indexer 被 SIGKILL/OOM 时 finally 不执行）

# 1. 后台启动 indexer
python -m everlingo mem indexer start &
idx_pid=$!

# 2. 等 indexer 就绪：轮询 indexer.mcp.url 出现并 URL 中端口可连
#    indexer.mcp.url 内容格式: http://127.0.0.1:<port>/mcp（见 server.py _run_indexer）
while [ ! -f "$MCP_URL_FILE" ]; do
  sleep 0.5
  if ! kill -0 "$idx_pid" 2>/dev/null; then
    echo "indexer exited before ready" >&2
    exit 1
  fi
done
while true; do
  URL=$(cat "$MCP_URL_FILE")
  host_port=$(echo "$URL" | sed -E 's#https?://127\.0\.0\.1:([0-9]+).*#\1#')
  if (echo > /dev/tcp/127.0.0.1/"$host_port") 2>/dev/null; then
    break
  fi
  sleep 0.5
  if ! kill -0 "$idx_pid" 2>/dev/null; then
    echo "indexer exited before ready" >&2
    exit 1
  fi
done

# 3. 后台启动 gateway（无参 = config-driven 多 channel，见 gateway.md 启动模式语义）
python -m everlingo gateway &
gw_pid=$!

# 4. 任一子进程退出则全退（exit code 透传）
wait -n "$idx_pid" "$gw_pid"
exit_code=$?
kill "$idx_pid" "$gw_pid" 2>/dev/null || true
exit "$exit_code"
