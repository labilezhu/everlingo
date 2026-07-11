# Current Sprint

## 进行中的任务

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"
- 2026-07-11 | Web Session Acceptor Session 超时回收机制：WebChannel 增加 DISCONNECT_GRACE（5 分钟无 SSE client）和 ABSOLUTE_IDLE_TIMEOUT（60 分钟绝对空闲）超时，recv() 返回 None 触发 QuitEvent；Gateway accept_session 加 done callback 清理 sessions 列表；web_acceptor create_session 加 done callback 清理 _channels；Session._channel_listener 加 QuitEvent 日志；WebChannel recv() 超时时输出 info 日志含 session id；测试 9 条（WebChannel 超时 5 条 + Gateway 清理 4 条）。
- 2026-07-07 (system-event-source) | Session/Chat Agent 系统事件源：新增 session_events.py（SessionEvent/SystemNotice/NoticeSink），Session 重构为事件队列模式（_channel_listener + post_event），MainAgent.ahandle_system_notice()，Writer system prompt 写入确认节 + _parse_write_confirmation + notify 到 Session，Gateway 路由桥（notify → post_notice → Session.post_event），测试 12 条用例。
- 2026-07-09 | Vault spec 布局改造：create_vault 改为将 vault_specs/default/*.md 逐文件 compile_prompt 后写入 $vault/spec/（而非单个 VAULT_SPEC.md 于 vault 根）；indexer is_excluded_vault_file 新增 spec/ 子目录排除规则；同步更新 agent 提示路径引用、vault_spec.md 自描述、spec 文档与测试。
