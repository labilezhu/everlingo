# 领域模型


## 用户模型

### 用户 Profile - UserProfile

在代码中， class 名称叫 `UserProfile`. 

结构示例：
```yaml
language:
    interface_language: zh-CN
    target_language: en
background:
	hobbies: 历史与文艺
dictionary_definition_style: |
    - 词意
    - 词源解释和历史
    - 词性（动词，名词……）如果是动词提供过去式，过去分词
```

#### 用户语言设置 - language

| 字段 | 类型 | 可选值 | 说明 | 约束 |
|------|------|--------|------|------|
| `interface_language` | string | `"zh-CN"`, `"en"` | 界面语言 | 必选。不能与 `target_language` 相同 |
| `target_language` | string | `"zh-CN"`, `"en"` | 目标学习语言 | 必选。不能与 `interface_language` 相同 |

##### 示例

```yaml
  "interface_language": "zh-CN",
  "target_language": "en"
```

##### 约束规则

- `interface_language` 和 `target_language` 均必须设置
- 两者不能相同

#### 用户背景 - background

| 字段        | 类型   | 可选值              | 说明                                                     | 约束 |
| ----------- | ------ | ------------------- | -------------------------------------------------------- | ---- |
| `hobbies`   | string |                     | 爱好描述。如：历史、文化、艺术、时事、科技、音乐、计算机 | 可选 |
| `residence` | string | 主要居住地区        |                                                          | 可选 |
| `gender`    | string | male, female, other | 性别                                                     | 可选 |

#### 词典解释风格 - dictionary_definition_style

类型：string 。可选配置

**字段说明：**

词典解释风格。示例值如：

- 词意
- 词源解释和历史
- 词性（动词，名词……）如果是动词提供过去式，过去分词







