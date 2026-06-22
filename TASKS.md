# Current Sprint

## 计划中的任务

## 可执行的任务


## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"
- 2026-06-22 09:56 | 增加对法语(fr)、德语(de)的支持：更新 models.py(LANGUAGES字典、字段描述)、agent.py(system prompt)、everlingo.example.yaml(注释)、DOMAIN.md(语言列表)；添加对应测试用例
- 2026-06-22 10:15 | 修复发送按钮脉冲动画的竞态条件：将 setPending(true) 移到 await sendMessage() 之前，确保按钮状态正确还原
- 2026-06-22 11:30 | 新增 USER.md 用户自由偏好笔记机制：新建 ~/.everlingo/USER.md（Markdown 自由文本，动态注入 system prompt）；新增 user_doc toolset（user_doc_get/user_doc_set，写前备份 .bak）；从 UserProfile 移除 background/dictionary_definition_style（旧配置残留字段被 pydantic 静默忽略，不迁移）；prompt 版本号重构到 setting.py（bump_prompt_version/get_prompt_version），conf_manager 与 user_doc 共用；MainAgent 刷新逻辑改为版本号 + 文件 mtime 双检（外部编辑 everlingo.yaml/USER.md 也能即时刷新 system prompt）；更新 DOMAIN.md/configuration.md/tools.md/agents-spec.md 及示例文件；新增 tests/test_user_doc.py 与 _build_system_prompt/重建相关测试





