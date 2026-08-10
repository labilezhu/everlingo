# 领域模型

## 语言

首先定义一下几个概念和数据模型：
- `语言`
    包括一个`语言代码`，如 `en` 。 和`语言名称`，如 `English` 。`语言代码`与`语言名称`的映射见： src/everlingo/models.py 中的 `LANGUAGES: dict` 
    举例：
    - `English`，代码：`en`
    - `日本語`，代码：`ja`
    - `简体中文`，代码：`zh-CN`
    - `Français`，代码：`fr`
    - `Deutsch`，代码：`de`    
- `目标学习语言(target_lang)`
    指本产品支持作为学习目标的语言。`可用目标学习语言` 包括： en/ja/zh-CN/fr/de
- `默认目标学习语言` 
  - 用户通过配置，指定的默认目标学习语言
- `笔记库已初始化`
  - 指某目标学习语言的笔记库（vault）已存在于 workspace 并注册到 indexer：`$workspace/memory/languages/$lang/` 存在且出现在 Vault MCP `list_vaults` 返回结果中
- `有效的默认目标学习语言配置`
  - 同时满足：`target_language` 非空、取值属于可用目标学习语言（en/ja/zh-CN/fr/de）、该语言的笔记库已初始化
- `界面语言(interface_language)`
    指本产品支持作为主要界面文字和语音的语言。`可用界面语言` 当前包括：`zh-CN` / `en`（未来扩展）。
    注意：`可用界面语言` 与 `可用目标学习语言` 是**两个独立集合**。界面语言的「语言代码 → 显示名」映射复用 `src/everlingo/models.py` 的 `LANGUAGES` 字典（单一真源），定义见 `AVAILABLE_INTERFACE_LANGUAGES` 常量。
    `interface_language` 为可选配置：留空时运行时按 OS locale 推断、兜底 `en`；非空时必须 ∈ `AVAILABLE_INTERFACE_LANGUAGES`。见 [ADR 20260806-interface-language-optional.md](ADR/20260806-interface-language-optional.md)。


## 用户模型

### 用户 Profile - UserProfile

在代码中， class 名称叫 `UserProfile`. 

结构示例：
```yaml
language:
    interface_language: zh-CN
    target_language: en
```

#### 用户语言设置 - language

| 字段 | 类型 | 可选值 | 说明 | 约束 |
|------|------|--------|------|------|
| `interface_language` | string | `"zh-CN"`, `"en"` | 界面语言 | 可选；留空时运行时按 OS locale 推断、兜底 `en`；非空时必须在可用界面语言内 |
| `target_language` | string | `"zh-CN"`, `"en"`, `"ja"`, `"fr"`, `"de"` | 目标学习语言 | 必选 |


##### 示例

```yaml
  "interface_language": "zh-CN",
  "target_language": "en"
```

##### 约束规则

- `interface_language` 可选（留空时推断，兜底 `en`），`target_language` 必须设置

### 用户自由偏好笔记 - USER.md

存放位置： `$workspace/memory/USER.md` 。Markdown 自由文本，由用户维护。

内容会被动态注入到 Agent 的 system prompt，用于个性化查词/翻译/答疑。

维护方式：
- 通过与 Agent 聊天，由 Agent 调用 `user_doc` 工具集更新
- 用户用外部编辑器直接编辑文件

一般的 use case 可包含（非强制结构）：
- 用户的个性化描述：偏好、职业、爱好、性别、地区、年龄
- 学习目标：如要考什么语言证书或评级，或职场英语
- 用户的查词的释义偏好
- 用户的翻译的偏好

约束：
- 文件不存在时视为空（不影响 system prompt）
- Agent 更新前应先读取当前内容（read-modify-write），整体覆盖写入
- 历史版本由 Memory Vault 的 git 版本控制（docs/impl-spec/worksplace/vault-version-control.md）统一回溯，不再单独生成 `.bak` 备份








