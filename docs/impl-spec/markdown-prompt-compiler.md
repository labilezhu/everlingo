# markdown prompt compiler

生成一个 markdown prompt compiler util。 在 src/everlingo/utils 中。

作用是根据 markdown 文件的 include 关系，生成出一个完整的 prompt string 。

注意要处理好 include 子文件的标题层级转换，要用 AST 不能用简单的 regex 替换。
如 src/everlingo/mem/vault/vault_spec.md 中有 `{{ include [参考 kb_items_spec.md](./kb_items_spec.md) }}` 。 


文件来源：
markdown 文件的来源类型，可以是 python package ，也可以是 filesystem 中的。引用时，如使用相对路径的，一定是与发起引用的文件相同来源类型。如果是是绝对路径，一定是 filesystem