# 领域模型

## 语言

语言的支持，可选项：
- `英语`，代码：`en`
- `日本語`，代码：`ja`
- `简体中文`，代码：`zh-CN`
- `法语`，代码：`fr`
- `德语`，代码：`de`

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
| `interface_language` | string | `"zh-CN"`, `"en"`, `"ja"`, `"fr"`, `"de"` | 界面语言 | 必选。不能与 `target_language` 相同 |
| `target_language` | string | `"zh-CN"`, `"en"`, `"ja"`, `"fr"`, `"de"` | 目标学习语言 | 必选。不能与 `interface_language` 相同 |


##### 示例

```yaml
  "interface_language": "zh-CN",
  "target_language": "en"
```

##### 约束规则

- `interface_language` 和 `target_language` 均必须设置
- 两者不能相同

### 用户自由偏好笔记 - USER.md

存放位置： `~/.everlingo/USER.md` 。Markdown 自由文本，由用户维护。

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
- 写入前由工具自动备份旧内容到 `USER.md.bak`








