

---

[Chrome Extension](docs/impl-spec/chrome-extension-spec.md) 在 session 过期后，会不停连接以下地址，以及在后端产生大量日志:
INFO:     172.28.0.1:34034 - "GET /api/session/3247b77e-859b-4880-b395-9ae7c8ddc4e3/events HTTP/1.1" 404 Not Found

应该仿照 [Web Chatbot](docs/impl-spec/web-chatbot.md) 的 “SSE 自动重连”。

---
