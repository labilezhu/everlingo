# markdown prompt compiler

生成一个 markdown prompt compiler util。 在 src/everlingo/utils 中。

作用是根据 markdown 文件的 include 关系，生成出一个完整的 prompt string 。

注意要处理好 include 子文件的标题层级转换，要用 AST 不能用简单的 regex 替换。
如 src/everlingo/mem/vault/vault_spec.md 中有 `{{ include [参考 kb_items_spec.md](./kb_items_spec.md) }}` 。 


文件来源：
markdown 文件的来源类型，可以是 python package ，也可以是 filesystem 中的。引用时，如使用相对路径的，一定是与发起引用的文件相同来源类型。如果是是绝对路径，一定是 filesystem

## 整体标题平移：`shift_headings(md, offset)`

`compile_prompt` 内部的 `context_level` 机制只调整 `{{ include }}` 进来的子文件标题，**不**调整入口文件自身的标题。当入口文件被作为片段注入到外层 prompt 的某个标题之下时（如 Memory Writer Agent 把 `vault_spec.md` 注入到 `## memory vault 结构` 之下），入口文件自身的 h1 会与外层 h2 冲突（子比父还浅）。

`shift_headings(md, offset)` 公开函数解决这个问题：对任意 markdown 文本（通常是 `compile_prompt` 的输出）整体平移标题层级。

- 基于 markdown-it AST，不会误判 fenced code block 内的 `#`（regex 版 `_demote_headings` 的局限）。
- `offset` 可正可负；标题级别钳制到 1..6。
- 与 `compile_prompt` 内部对 include 子文件的平移互补，可叠加使用。
