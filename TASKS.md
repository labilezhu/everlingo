# Current Sprint

## 进行中的任务

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"
- 2026-06-28 | Memory Extract Agent 可行性版本：实现 src/everlingo/mem/agents/mem_extract_agent.py（daemon thread + queue 异步消费、structured output、post-process 透传字段、session_seen_headwords 累积、USER.md 降级注入用于筛选判断、失败 logger.exception 丢弃不调 writer、本阶段精简筛选规则仅"用户明确要求记住"+"纠正事项"）+ src/everlingo/mem/agents/mem_entries.py（ExtractInput / MemoryEntry / ExtractLLMOutput / EntryWriterProtocol）；MainAgent 新增 session_id kwarg，__init__ 创建并 start 自己的 Extract Agent，invoke 返回前 submit ExtractInput（最近 20 轮 context_messages）；gateway.memory_writer 模块级单例（StubMemoryWriter 仅 info 日志记数量，Writer Agent 待实现）；tests/test_mem_extract_agent.py 30 例（覆盖透传字段、session_seen_headwords 累积、20 轮截取、submit 非阻塞、LLM 异常丢弃且后续继续、USER.md 空跳过、日志全字段输出、MainAgent 接线）
- 2026-06-27 11:42 | WechatChannel: SDK credentials 文件保存到 $workspace/plugins/channels/wechat_channel/credentials/credentials.json，init() 自动创建目录；新增 workspace.plugins_dir() 访问器
- 2026-06-27 17:40 | markdown prompt compiler：基于 markdown-it-py AST 实现 src/everlingo/utils/md_prompt_compiler.py，支持 `{{ include [label](path) }}` 独占段落指令、标题层级转换（子文件最浅标题→context_level+1，整体平移并钳制 1..6）、FilesystemSource 与 PackageSource、绝对路径强制 filesystem、循环检测与缺失文件报错；frontmatter 编译时剥离；输出为 markdown；新增 tests/test_md_prompt_compiler.py（20 例）
