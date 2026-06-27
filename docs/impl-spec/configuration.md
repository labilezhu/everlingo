# 配置实现

有两种配置的方法：
- Environment Variables
- 配置文件


## Environment Variables

Environment Variables 说明，参考[配置参考](/user-docs/reference/configuration.md) 中 `## Environment Variables` 一节。

根据上面的 `Environment Variables` 列表。生成一个带注释和示例取值的文件，保存在本 codebase 的 `/.env.example` 文件中。


### 代码实现
`src/everlingo/config.py` -> `get_llm_config()`


## 配置文件

所有配置文件，均在 [workspace](/docs/impl-spec/worksplace/workspace.md) 下。

配置文件位置： `$workspace/everlingo.yaml` 。 配置文件使用 yaml 格式。

配置项说明，参考[配置参考](/user-docs/reference/configuration.md) 中 `## 配置文件` 一节。

根据 `配置项说明` 内容。生成一个带注释和示例取值的 yaml 文件，保存在本 codebase 的 `/everlingo.example.yaml` 中。


### 配置实现的基础选型

#### 数据对象定义
选用 `pydantic` 而不是 `dataclass` 来定义数据对象。它需要支持
- 生成 JSON Schema。
- 完成校验
- 使用 Pydantic 的 `Field()` 为数据对象字段元信息，包括字段描述与可选的示例
