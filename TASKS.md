# Current Sprint

## 进行中的任务

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"
- 2026-07-15 | tags 搜索全面升级：新增 `document_tags` 关系表精确匹配（AND/OR），替换旧 `d.tags LIKE` 子串过滤；新增 `tags_op` 参数；新增 `GET /{lang}/tags` 端点和 MCP `list_tags` 工具返回 tag 字典及计数；schema 升级至 v3，DB 升级后需 `reindex --rebuild` 回填表数据。
- 2026-07-15 | 同步更新 MCP 规范文档（`vault-mcp-spec.md`/`vault-mcp-spec-tools.yaml`）反映 `list_tags` 和 `tags_op`；更新 `search-api-spec.md` 添加 `tags_op` 请求字段描述；更新 `memory-vault-embedding-spec.md` knn 签名。
- 2026-07-15 | **LLM 调用可靠性加固**：`llm.py` 注入 httpx `AsyncClient` + `Client` 带 response event hook，非 JSON 响应体自动记录状态码与前 500 字节到 warning 日志；`agent.py` 新增 `_invoke_llm_with_retry`，对 `JSONDecodeError`/`httpx.HTTPError`/`InternalServerError`/`RateLimitError`/`APITimeoutError`/`APIConnectionError` 重试 2 次（指数退避），永久性错误（`AuthenticationError`/`BadRequestError` 等）透传不重试；重试耗尽返回 "AI 服务暂时不可用，请稍后重试" 友好提示。新增 `tests/test_agent_retry.py` 8 用例、`tests/test_llm_malformed_logging.py` 8 用例。

