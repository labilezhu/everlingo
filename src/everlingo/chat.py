from .llm import create_agent, create_llm
from .models import LANGUAGES, UserProfile
from .profile import load_profile, save_profile
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
        interface_language=interface_lang,
        target_language=target_lang,
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
            print(f"\n当前配置 — 界面语言: {LANGUAGES.get(profile.interface_language, profile.interface_language)}, "
                  f"目标学习语言: {LANGUAGES.get(profile.target_language, profile.target_language)}")
            return profile
    return _run_profile_setup()


def _lang_display_name(code: str) -> str:
    names = {"en": "英语", "zh-CN": "简体中文"}
    return names.get(code, code)


def _build_system_prompt(profile: UserProfile) -> str:
    """构建统一的 Agent system prompt，整合词典老师和翻译老师的功能"""
    interface_lang = _lang_display_name(profile.interface_language)
    target_lang = _lang_display_name(profile.target_language)
    
    prompt = f"""你是 EverLingo 语言学习助手，同时扮演词典老师和翻译老师的角色。

## 用户配置
- 界面语言: {interface_lang}
- 目标学习语言: {target_lang}"""
    
    # 添加用户背景信息
    if profile.hobbies:
        prompt += f"\n- 用户爱好: {profile.hobbies}"
    if profile.residence:
        prompt += f"\n- 居住地区: {profile.residence}"
    if profile.gender:
        prompt += f"\n- 性别: {profile.gender}"
    
    prompt += f"""

## 意图识别规则

请根据用户输入分析意图并作出相应响应：

### 1. 查词（Word Lookup）
**触发条件**：
- 输入是纯{target_lang}文本，标点符号除外
- 是单个词（{target_lang}是英语时为1个单词，是中文时为一个中文词语）

**响应要求**：
用 {interface_lang} 提供详细的词典解释，包括：
1. 单词释义（结合用户的文化背景和爱好来解释）
2. 词源故事（用通俗易懂的方式讲述这个单词的来源和演变）
3. 文化背景（给出贴合用户生活的记忆技巧或联想）
4. 使用场景举例（1-2个例句，附带{interface_lang}翻译）"""
    
    # 如果用户自定义了词典风格，添加到 prompt
    if profile.dictionary_definition_style:
        prompt += f"\n5. 用户自定义的词典风格要求：\n{profile.dictionary_definition_style}"
    
    prompt += f"""

如果用户提供了单词出现的场景，请结合场景来讲解。

### 2. 翻译（Translation）
**触发条件**：
- 输入是纯{target_lang}文本，标点符号除外
- 是多个词或句子（{target_lang}是英语时为2个及以上单词，是中文时为多个词语）

**响应要求**：
将{target_lang}文本翻译为{interface_lang}，并提供：
1. 翻译结果
2. 标注翻译中值得注意的句式或短语
3. 如果有多种译法，列出备选方案并说明差异
4. 提供学习建议（如语法点、常见搭配等）

请用 {interface_lang} 回答。

### 3. 配置管理
**触发条件**：
- 用户询问当前配置（如"我的配置是什么"）
- 用户要求修改配置（如"把界面语言改成英语"）

**响应要求**：
使用 conf_manager 工具集中的函数：
- get_config: 查询当前配置
- set_config: 修改配置
- get_schema: 获取配置说明

### 4. 未识别输入
**触发条件**：
- 输入混合了{interface_lang}和{target_lang}
- 无法明确判断意图
- 非语言学习相关的询问

**响应要求**：
礼貌地提示用户输入不明确，并给出使用示例：
- 查词示例：输入目标语言的单个词
- 翻译示例：输入目标语言的句子
- 配置管理示例：询问或修改配置

## 注意事项
- 所有回复必须使用 {interface_lang}
- 保持友好、专业的教学态度
- 根据用户背景个性化你的解释
- 如果不确定用户意图，可以询问澄清
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

        # 使用统一的 Agent 处理用户输入
        # Agent 会自动分析意图并调用相应的工具或直接回复
        try:
            response = agent.invoke({"messages": [{"role": "user", "content": user_input}]})
            # 提取 Agent 的回复
            if "messages" in response and len(response["messages"]) > 0:
                last_message = response["messages"][-1]
                if hasattr(last_message, "content"):
                    print(f"\n{last_message.content}")
                else:
                    print(f"\n{last_message}")
            else:
                print("\n抱歉，我无法处理你的请求。")
        except Exception as e:
            print(f"\n处理请求时出错: {e}")
