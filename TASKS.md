# Current Sprint

## 进行中的任务
- 

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"
- 2026-06-27 11:42 | WechatChannel: SDK credentials 文件保存到 $workspace/plugins/channels/wechat_channel/credentials/credentials.json，init() 自动创建目录；新增 workspace.plugins_dir() 访问器
- 2026-06-27 17:40 | markdown prompt compiler：基于 markdown-it-py AST 实现 src/everlingo/utils/md_prompt_compiler.py，支持 `{{ include [label](path) }}` 独占段落指令、标题层级转换（子文件最浅标题→context_level+1，整体平移并钳制 1..6）、FilesystemSource 与 PackageSource、绝对路径强制 filesystem、循环检测与缺失文件报错；frontmatter 编译时剥离；输出为 markdown；新增 tests/test_md_prompt_compiler.py（20 例）
