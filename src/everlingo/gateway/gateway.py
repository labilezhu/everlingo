# ref: gateway.md — Gateway 进程入口
# ref: app-entry.md — 应用主入口

import argparse
import asyncio

from ..log_utils import setup_logging
from ..models import LANGUAGES, UserProfile
from ..setting import load_profile, save_profile
from .session_acceptor import StdioSessionAcceptor, WechatSessionAcceptor
from .web_acceptor import WebSessionAcceptor
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

class Gateway:
    """Gateway 服务。

    ref: /docs/impl-spec/gateway.md
    负责：
    - 按启动参数要求，创建相应的 Session Acceptor
    - 维护和管理一个 Session 列表
    - 接收和处理来自 Session Acceptor 的 session 创建请求
    """

    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self._profile: UserProfile | None = None

    async def accept_session(
        self, channel, session_id: str
    ) -> asyncio.Task:
        """处理 Session Acceptor 提交的 session 创建请求。

        ref: /docs/impl-spec/gateway.md — session 创建请求的处理
        如果 session_id 已存在则视为 resume，否则创建新的 Session。
        创建/恢复 session 后启动其消息循环协程并返回 task。
        """
        if session_id in self.sessions:
            self.sessions[session_id].channel = channel
            session = self.sessions[session_id]
        else:
            agent = MainAgent(self._profile)
            session = Session(channel=channel, agent=agent, id=session_id)
            self.sessions[session_id] = session

        return asyncio.create_task(session.run())

    async def run(self, channel_type: str = "stdio") -> None:
        """Gateway 主入口。

        Args:
            channel_type: "stdio" 或 "wechat" 或 "web"
        """
        setup_logging()
        try:
            self._profile = _ensure_profile()
        except ValueError as e:
            print(f"\n配置错误: {e}")
            return

        if channel_type == "wechat":
            acceptor = WechatSessionAcceptor()
        elif channel_type == "web":
            acceptor = WebSessionAcceptor()
        else:
            acceptor = StdioSessionAcceptor()

        task = await acceptor.start(self)
        await task


def main() -> None:
    """Gateway 进程入口。

    用法：
        gateway --channel_stdio   # 启动 Stdio Channel（默认）
        gateway                   # 同上，默认启动 Stdio Channel
        gateway --channel_wechat  # 启动 Wechat Channel
        gateway --channel_web     # 启动 Web Channel（FastAPI + 前端）

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
        help="启动 Wechat Channel",
    )
    channel_group.add_argument(
        "--channel_web",
        action="store_true",
        default=False,
        help="启动 Web Channel（FastAPI + 前端）",
    )
    args = parser.parse_args()

    if args.channel_wechat:
        channel_type = "wechat"
    elif args.channel_web:
        channel_type = "web"
    else:
        channel_type = "stdio"
    gateway = Gateway()
    asyncio.run(gateway.run(channel_type=channel_type))


if __name__ == "__main__":
    main()
