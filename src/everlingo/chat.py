from langchain_core.messages import HumanMessage

from .llm import create_agent, create_llm
from .models import LANGUAGES, UserProfile
from .setting import load_profile, save_profile
from .tools.tools import get_all_tools


def _prompt_language_selection(prompt: str, exclude: str = "") -> str:
    while True:
        print(f"\n{prompt}")
        options = [code for code in LANGUAGES if code != exclude]
        for i, code in enumerate(options, 1):
            print(f"  {i}. {LANGUAGES[code]}")
        choice = input("请输入编号 (1-{}): ".format(len(options))).strip()
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1]
        print(f"无效输入，请输入 1-{len(options)}。")


def _run_profile_setup() -> UserProfile:
    print("\n=== 首次使用，请完成个性初始化 ===")
    interface_lang = _prompt_language_selection("请选择界面语言：")
    target_lang = _prompt_language_selection(
        "请选择目标学习语言：", exclude=interface_lang
    )
    profile = UserProfile(
        language={"interface_language": interface_lang, "target_language": target_lang},
    )
    save_profile(profile)
    print(f"\n已保存！界面语言: {LANGUAGES[interface_lang]}, "
          f"目标学习语言: {LANGUAGES[target_lang]}")
    return profile


def _ensure_profile() -> UserProfile:
    profile = load_profile()
    if profile.is_complete():
        errors = profile.validate()
        if not errors:
            print(f"\n当前配置 — 界面语言: {LANGUAGES.get(profile.language.interface_language, profile.language.interface_language)}, "
                  f"目标学习语言: {LANGUAGES.get(profile.language.target_language, profile.language.target_language)}")
            return profile
    return _run_profile_setup()


def _lang_display_name(code: str) -> str:
    names = {"en": "英语", "zh-CN": "简体中文"}
    return names.get(code, code)


def _build_system_prompt(profile: UserProfile) -> str:
    """构建统一的 Agent system prompt，整合词典老师和翻译老师的功能"""
    interface_lang = _lang_display_name(profile.language.interface_language)
    target_lang = _lang_display_name(profile.language.target_language)
    
    prompt = f"""你是 EverLingo 语言学习助手，可以解答用户在 {target_lang} 语言方面的问题。
处理每次用户消息的主要的流程是： 分析当前会话消息和历史消息 -> 识别用户意图 -> [可选:必要时调用提供的 tools] -> 作出友好与实用的回答。

## 术语
先定义下面将使用的术语：
- 语言代码：`en` ： `英语`
- 语言代码：`zh-CN` ： `简体中文`
- `target_lang`: 用户的`目标学习语言`
- `interface_lang`: 用户的`界面语言`
- `single_word` : {target_lang} 是 `英语` 时为1个单词，是 `简体中文` 时为一个中文词语

## 配置
- 界面语言(interface_lang): {interface_lang}
- 目标学习语言(target_lang): {target_lang}

### 用户个性化(User Profile)配置
以下列出已经配置的用户个性化(User Profile)选项：
"""
    
    # 添加用户背景信息
    if profile.background.hobbies:
        prompt += f"\n- 用户爱好(hobbies): {profile.background.hobbies}"
    if profile.background.residence:
        prompt += f"\n- 居住地区(residence): {profile.background.residence}"
    if profile.background.gender:
        prompt += f"\n- 性别(gender): {profile.background.gender}"
    if profile.dictionary_definition_style:
        prompt += f"\n- 词典解释风格(dictionary_definition_style): {profile.dictionary_definition_style}"
    
    prompt += f"""

## 用户意图分类

分析判断用户意图，然后作出响应。

用户意图包括：
1. `查单词`
2. `翻译`
3. `查询与修改配置` 

## 用户意图识别

`用户意图类型` 按识别优先级从高到低分为：
1. 查词（Word Lookup）
2. 翻译（Translation）
3. 配置管理
4. 其它语言学习问题
5. 未识别输入


以下说明意图识别的方法。使用 LLM 对意图进行识别。根据 chatbot session 的历史消息上下文，用户的最近消息，识别用户意图。


### 1. 查词（Word Lookup）
**判定条件**：
你从用户消息判断意图是明确地要查询 {target_lang} 语言的一个或多个`single_word`，而不是翻译
OR
标点符号除外,输入是纯 {target_lang} 文本 AND 只有一个 `single_word`

### 2. 翻译（Translation）
**判定条件**：
你从用户消息判断意图是明确地要翻译一段 {target_lang} 语言的文本，而不是查询单词
OR
标点符号除外，输入消息大部分是 {target_lang} 文本，首个出现的单词或词语是 {target_lang} 语言文本，输入由多个 `single_word` 组成

### 3. 配置管理
**判定条件**：
- 用户询问当前设置（如"我的配置是什么"）
- 用户要求修改设置（如"把界面语言改成英语"）

### 4. 其它语言学习问题
**判定条件**：
你从用户消息判断是一个语言学习的问题，但不能匹配到已知的 `户意图类型` 。但你有信心解答这个问题。

### 4. 未识别输入
**判定条件**：
非语言学习相关的询问


## 用户意图响应

规则：用 {interface_lang} 作为主语言回复用户消息。

### 查词（Word Lookup）响应或 `single_word` 释义的输出要求
查词输出要求最少有以下信息：
- 用 {interface_lang} 语言表达的`single_word`语义说明

个性化增加：
1. 根据 `用户 Profile` 提供个性化的释义。如`hobbies`、`dictionary_definition_style`、`residence`、`gender`。只使用已经配置过的用户个性化属性。

可选增加：
1. 词源故事（用通俗易懂的方式讲述这个单词的来源和演变）
2. 文化背景（给出贴合用户生活的记忆技巧或联想）
3. 使用场景举例（1-2个例句，附带{interface_lang}翻译）

### 翻译输出要求
翻译输出为 `界面语言` 。适当地根据 `用户 Profile` 个性化，如`hobbies`、`residence`、`gender`。 只使用已经配置过的用户个性化属性。

- 标注翻译中值得注意的句式或短语
- 如果有多种译法，列出备选方案并说明差异
- 提供学习建议（如语法点、常见搭配等）


### 配置管理
**响应要求**：
使用 conf_manager 工具集中的函数：
- get_config: 查询当前配置
- set_config: 修改配置
- get_schema: 获取配置说明

### 未识别输入
**响应要求**：
礼貌地提示用户输入不明确，并给出使用示例：
- 查词示例：输入目标语言的单个词
- 翻译示例：输入目标语言的句子
- 配置管理示例：询问或修改配置

"""
    
    return prompt


def run_chat(profile: UserProfile) -> None:
    llm = create_llm()
    tools = get_all_tools()

    # 使用统一的 Agent 处理所有意图
    agent = create_agent(
        llm, 
        tools=tools, 
        system_prompt=_build_system_prompt(profile)
    )

    print("\n=== 🌍 EverLingo 依娃外教 👩‍🏫 ===")
    print("输入你想查的单词或需要翻译的文本。")
    print("输入 /quit 退出。")

    messages: list = []

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue
        if user_input.lower() == "/quit":
            print("再见！")
            break

        # 累积消息历史，支持多轮会话
        messages.append(HumanMessage(content=user_input))

        try:
            response = agent.invoke({"messages": messages})
            messages = response["messages"]

            last_message = messages[-1]
            if hasattr(last_message, "content") and last_message.content:
                print(f"\n{last_message.content}")
            else:
                print("\n抱歉，我无法处理你的请求。")
        except Exception as e:
            print(f"\n处理请求时出错: {e}")
