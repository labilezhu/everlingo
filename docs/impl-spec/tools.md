# Tools

## 管理配置 - configuration_manager

tool name: configuration_manager
tool description: 管理配置

### functions

#### 获取配置元信息描述与schema 
function name: get_schema
function description: 获取配置元信息描述与schema 
returns: yaml 格式的配置示例。直接返回 [/everlingo.example.yaml](/everlingo.example.yaml) 内容。

#### 查询配置
function name: get_config
function description: 查询配置
returns: 返回当前生效的 yaml 格式的配置文件内容

#### 修改配置
function name: set_config
function description: 修改多个配置项目。
parameters:
    configToBeMerged: string
returns: 
    config: string 。 成功 merged 后的 yaml 格式的配置文件内容。
    error: string。 如果失败，返回原因。

可以管理的配置和相关描述与约束，见 [configuration.md](/docs/impl-spec/configuration.md)。 一定要对用户的输入进行配置约束检查。            

调用例子：
configToBeMerged :
```yaml
sys_setting:
    openai_model: deepseek
user_profile:
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