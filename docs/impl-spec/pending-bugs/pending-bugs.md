# Pending Bugs




---

- ~~Chrome Extension 在 session 过期后，会不停连接以下地址，以及在后端产生大量日志:
  INFO:     172.28.0.1:34034 - "GET /api/session/3247b77e-859b-4880-b395-9ae7c8ddc4e3/events HTTP/1.1" 404 Not Found
  应该仿照 Web Chatbot 的 “SSE 自动重连”。~~  
  **已解决** - 2026-07-27：`extension/src/services/sseClient.ts:connectSSE` 的 `onerror` 原是 `return 0`（库解释为"0ms 后立即重试"），修正为检测 404 → `throw SessionExpiredError` 停止重试 + `onStatus({state:'session_expired'})`，网络瞬时错误走指数退避。详见 [chrome-extension-spec.md §5.6](../chrome-extension-spec.md)。

---

