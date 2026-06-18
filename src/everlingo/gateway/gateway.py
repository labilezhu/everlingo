# ref: gateway.md — Gateway 进程入口
# ref: app-entry.md — 应用主入口

import argparse
import asyncio

from ..log_utils import setup_logging
from ..models import LANGUAGES, UserProfile
from ..setting import load_profile, save_profile
from .channels.stdio_channel import StdioChannel
from .session import Session
from ..agents.agent import MainAgent


# ── Profile 初始化向导（从 chat.py 迁入） ────────────────────────────────────

def _prompt_language_selection(prompt: str, exclude: str = "") -> str:
    """命令行交互式语言选择。"""
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
    """首次使用时引导用户完成个性化初始化。"""
    print("\n=== 首次使用，请完成个性初始化 ===")
    interface_lang = _prompt_language_selection("请选择界面语言：")
    target_lang = _prompt_language_selection(
        "请选择目标学习语言：", exclude=interface_lang
    )
    profile = UserProfile(
        language={"interface_language": interface_lang, "target_language": target_lang},
    )
    save_profile(profile)
    print(
        f"\n已保存！界面语言: {LANGUAGES[interface_lang]}, "
        f"目标学习语言: {LANGUAGES[target_lang]}"
    )
    return profile


def _ensure_profile() -> UserProfile:
    """加载 Profile；若未完成配置则进入初始化向导。"""
    profile = load_profile()
    if profile.is_complete():
        errors = profile.validate()
        if not errors:
            print(
                f"\n当前配置 — 界面语言: "
                f"{LANGUAGES.get(profile.language.interface_language, profile.language.interface_language)}, "
                f"目标学习语言: "
                f"{LANGUAGES.get(profile.language.target_language, profile.language.target_language)}"
            )
            return profile
    return _run_profile_setup()


# ── Gateway ──────────────────────────────────────────────────────────────────

async def _run_stdio() -> None:
    """启动 Stdio Channel 的 Gateway。

    ref: /docs/impl-spec/gateway.md
    ref: /docs/impl-spec/app-entry.md
    """
    setup_logging()
    try:
        profile = _ensure_profile()
    except ValueError as e:
        print(f"\n配置错误: {e}")
        return

    channel = StdioChannel()
    agent = MainAgent(profile)
    session = Session(channel, agent)
    await session.run()


def main() -> None:
    """Gateway 进程入口。

    用法：
        gateway --channel_stdio   # 启动 Stdio Channel（默认）
        gateway                   # 同上，默认启动 Stdio Channel
        gateway --channel_wechat  # 启动 Wechat Channel（暂不实现）

    ref: /docs/impl-spec/gateway.md
    """
    parser = argparse.ArgumentParser(description="EverLingo Gateway")
    channel_group = parser.add_mutually_exclusive_group()
    channel_group.add_argument(
        "--channel_stdio",
        action="store_true",
        default=False,
        help="启动 Stdio Channel（默认）",
    )
    channel_group.add_argument(
        "--channel_wechat",
        action="store_true",
        default=False,
        help="启动 Wechat Channel（暂未实现）",
    )
    args = parser.parse_args()

    if args.channel_wechat:
        print("Wechat Channel 暂未实现。")
        return

    # 默认或指定 --channel_stdio 均启动 Stdio Channel
    asyncio.run(_run_stdio())


if __name__ == "__main__":
    main()
