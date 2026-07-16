# Current Sprint

## 进行中的任务

## 完成的任务
格式：完成日期与时间(GMT+8 timezone) | 任务描述 。 示例： " - 2026-06-20 19:28 | 生成主入口代码"
 - 2026-07-16 18:52 | create_vault: 从只 copy spec/*.md 改为递归 copy templates/default/*（spec/*.md 走 compile_prompt，其余 raw copy）；返回字段 spec_written → files_written（int）；同步更新设计文档
 - 2026-07-16 18:59 | create_vault: spec/*.md 有 frontmatter 的原样 copy 保留 frontmatter，不再走 compile_prompt（compile_prompt 会剥离 frontmatter）；用 split_frontmatter 检测；补 spec/index.md 断言
 - 2026-07-16 21:15 | fix: _parse_write_confirmation 因 AIMessage.content 为 list 类型时报 AttributeError（list 无 .strip 方法）；添加 list→str 归一化处理并跳过空内容
