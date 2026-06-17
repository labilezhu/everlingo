# Tools


## langchain tool 实现

langchain tools 的写法：

```python
@tool("$toolset_$function_name:")  # 即加入 toolset name 作为前缀
def search(query: str) -> str:
    """Search the web for information."""
    return f"Results for: {query}"
```

每个 toolset 应该对应一个独立的 python 文件。文件应该放于 `/src/everlingo/tools` 目录。如 `/src/everlingo/tools/conf_manager.py`。

 `/src/everlingo/tools/tools.py` 应该是一个可以获取所有 tools 的注册表。为 langchain agent 提供总的 tools 列表。
 ```python
 def get_tools() -> list:
        return [x,y,z]
    return []
 ```

### tools 调用日志
每个 tool 的调用，均需要记录日志。logging level 为 debug。内容和格式如下：
```log
tool_name: xyz , parameters: argName1=argValue1,... , return: xyz
```


# Toolsets(工具集)

以下包括多个 toolset(工具集)。 

## 管理配置 - conf_manager

toolset name: conf_manager
toolset description: 管理配置

### functions

#### get_schema
function name: get_schema
function description: 获取配置元信息描述与schema 
returns: yaml 格式的配置示例。直接返回 [/everlingo.example.yaml](/everlingo.example.yaml) 内容。

#### get_config
function name: get_config
function description: 查询配置
returns: 返回当前生效的 yaml 格式的配置文件内容

#### set_config
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

## 系统时间 - clock

tool name: clock
tool description: 系统时间


### functions

#### get_datetime
function name: get_datetime
function description: 返回当前的系统时间
returns: string . 格式：日期与时间(Shanghai timezone) 。示例： `2026-06-20 19:28:59` 