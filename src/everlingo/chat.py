from .models import UserProfile, LANGUAGES
from .profile import load_profile, save_profile
from .intent import IntentAnalyzer
from .dict_teacher import DictionaryTeacher
from .trans_teacher import TranslationTeacher


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


def run_chat(profile: UserProfile) -> None:
    from .llm import create_llm

    llm = create_llm()
    analyzer = IntentAnalyzer(profile)
    dict_teacher = DictionaryTeacher(llm, profile)
    trans_teacher = TranslationTeacher(llm, profile)

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
