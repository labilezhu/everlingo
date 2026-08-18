# Tasks

## 计划的任务

（无）

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"
- 2026-08-18 | Release 0.1.2-rc.3：全仓版本号 0.1.2-rc.2 → 0.1.2-rc.3（__init__.py / MePage.tsx / ws_master·ws_router app.py / pyproject.toml=0.1.2rc3 / vault_spec×2 / README×2 / user-docs×3 / router-master 部署文档 EVERLINGO_VER）；Chrome 扩展 manifest.json=0.1.2.3、package.json=0.1.2-rc.3、package-lock 经 npm install 同步并重新 build 验证；发布 tag v0.1.2-rc.3；VERSION_HISTORY.yaml 0.1.2-rc.3 标记 released + 插入 0.1.2-rc.4。
- 2026-08-18 | Wechat Channel 图片接收与 LLM 分析：新增 `image_store.sniff_image_mime()` 与 `vision_service.eager_warm()`（web_acceptor 复用去重）；`wechat_channel` 队列改装 `_WechatIncoming`（text + image_bytes），CDN 图片下载在 bot 线程回调完成，嗅探/落盘/预热在 Session loop 内完成（规避 Vision `in_flight` Future 跨 loop），`recv_envelope` 构造带 `chat.attachments` 的 envelope，`get_metadata.supported_image=True`，构造参数新增 `session_id`；runtime 先 mint session_id 再构造 channel；新增/更新测试并回填 ADR 与 spec 文档。详见 docs/ADR/20260818-image-chat-wechat.md

