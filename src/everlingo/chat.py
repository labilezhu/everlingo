from .llm import create_agent, create_llm
from .models import LANGUAGES, UserProfile
from .profile import load_profile, save_profile
from .dict_teacher import DictionaryTeacher
from .trans_teacher import TranslationTeacher
from .tools.tools import get_tools


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


def _build_dict_system_prompt(profile: UserProfile) -> str:
    return (
        f"你是一位专业的词典老师。请用 {_lang_display_name(profile.interface_language)} 解释以下单词。\n"
        f"用户的目标学习语言是 {_lang_display_name(profile.target_language)}。\n"
        "请提供：\n"
        f"1. 单词释义（用 {_lang_display_name(profile.interface_language)} 解释，兼顾用户可能的母语文化背景）\n"
        "2. 词源故事（用通俗易懂的方式讲述这个单词的来源和演变）\n"
        "3. 文化背景（结合中文用户的文化背景，给出贴合生活的记忆技巧或联想）\n"
        f"4. 使用场景举例（1-2 个例句，带 {_lang_display_name(profile.interface_language)} 翻译）\n"
        "如果用户提供了单词出现的场景，请结合场景来讲解。"
    )


def _build_trans_system_prompt(profile: UserProfile) -> str:
    interface_lang = _lang_display_name(profile.interface_language)
    target_lang = _lang_display_name(profile.target_language)
    return (
        "你是一位专业的翻译老师。\n"
        f"用户界面语言: {interface_lang}\n"
        f"目标学习语言: {target_lang}\n"
        "请将以下{source_lang}文本翻译成{target_lang}。\n"
        "翻译后请：\n"
        "1. 标注翻译中值得注意的句式或短语\n"
        "2. 如果有多种译法，列出备选\n"
        f"请用 {interface_lang} 回答。"
    )


def run_chat(profile: UserProfile) -> None:
    llm = create_llm()
    tools = get_tools("conf_manager")

    dict_agent = create_agent(
        llm, tools=tools, system_prompt=_build_dict_system_prompt(profile)
    )
    trans_agent = create_agent(
        llm, tools=tools, system_prompt=_build_trans_system_prompt(profile)
    )

    dict_teacher = DictionaryTeacher(dict_agent, profile)
    trans_teacher = TranslationTeacher(trans_agent, profile)

    print("\n=== EverLingo 依娃外教 ===")
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

        from .intent import IntentAnalyzer
        analyzer = IntentAnalyzer(profile)
        intent = analyzer.analyze(user_input)
        if intent == "word":
            print("\n--- 查词中... ---")
            result = dict_teacher.lookup(user_input)
            print(f"\n{result.definition}")
        elif intent == "translation":
            print("\n--- 翻译中... ---")
            result = trans_teacher.translate(user_input)
            print(f"\n{result.target_text}")
        else:
            print("\n未识别的输入。输入目标语言中的单词查词典，输入句子翻译。")
