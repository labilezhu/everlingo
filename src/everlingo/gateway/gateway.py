# ref: gateway.md — Gateway 进程入口
# ref: app-entry.md — 应用主入口
# ref: docs/impl-spec/memory-extract-agent-spec.md — 异步执行
# ref: docs/impl-spec/memory-writer-agent-spec.md — 异步执行（Writer 单例）

import argparse
import asyncio
import logging
import signal

from ..log_utils import setup_logging
from ..models import LANGUAGES, UserProfile
from ..setting import (
    channel_enabled,
    get_web_listener,
    load_profile,
    save_profile,
)
from ._memory_writer import memory_writer
from .session_acceptor import SessionAcceptor, StdioSessionAcceptor
from .session_events import SystemNotice
from .web_acceptor import WebSessionAcceptor
from .wechat_admin.runtime import STOP_TIMEOUT, WechatRuntime
from .session import Session


logger = logging.getLogger(__name__)


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
    - 接收后台 Agent（Memory Writer 等）的系统通知并路由到对应 Session
    """

    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self._profile: UserProfile | None = None
        # wechat channel 的 in-process 托管者（供 workspace_console router 控制）
        self.wechat_runtime: WechatRuntime | None = None
        # 注册为 NoticeSink（供 Memory Writer 跨线程推送通知）
        memory_writer.set_notice_sink(self)

    # ── NoticeSink ───────────────────────────────────────────────

    def notify(
        self,
        *,
        session_id: str,
        source: str,
        updated_files: list[str],
        update_summary: str,
        title: str,
        lang: str,
    ) -> None:
        """Implement NoticeSink Protocol：路由后台通知到对应 Session。

        跨线程安全（由 Session.post_event 的 call_soon_threadsafe 保证）。
        session 不存在时丢弃 + 日志警告（与 daemon "可接受丢失"语义一致）。
        """
        session = self.sessions.get(session_id)
        if session is None:
            logger.warning(
                "notice for unknown session %s (%s=%s), dropped",
                session_id, source, title,
            )
            return
        notice = SystemNotice(
            source=source,
            updated_files=updated_files,
            update_summary=update_summary,
            title=title,
            lang=lang,
        )
        session.post_event(notice)

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
            session = Session(channel=channel, profile=self._profile, id=session_id)
            self.sessions[session_id] = session

        task = asyncio.create_task(session.run())
        task.add_done_callback(
            lambda _t, _sid=session_id: self._cleanup_session(_sid)
        )
        return task

    def _cleanup_session(self, session_id: str) -> None:
        """Session 退出后从 sessions 列表中移除。"""
        removed = self.sessions.pop(session_id, None)
        if removed is not None:
            logger.info("Session %s cleaned up", session_id)

    def _request_shutdown(self) -> None:
        """触发所有托管 runtime 的 graceful shutdown（supervisor task 退出）。"""
        if self.wechat_runtime is not None:
            self.wechat_runtime.request_shutdown()

    def _build_acceptors(self, channel_type: str | None) -> list[SessionAcceptor]:
        """按启动模式组装 acceptor 列表。

        ref: gateway.md 启动模式语义 / workspace-console/architecture.md §4.2
        - explicit flag → 单 channel（--channel_web 额外带 idle WechatRuntime）
        - 无参（None）→ config-driven 多 channel
        """
        acceptors: list[SessionAcceptor] = []
        if channel_type == "wechat":
            # standalone：忽略 config；bot 崩溃 / SIGINT 时退出进程
            self.wechat_runtime = WechatRuntime(
                auto_start=True, on_bot_exit=self._request_shutdown
            )
            acceptors.append(self.wechat_runtime)
        elif channel_type == "web":
            # 仅 web；带 idle WechatRuntime 供 console 手动启停
            listener = get_web_listener()
            acceptors.append(
                WebSessionAcceptor(host=listener.interface, port=listener.port)
            )
            self.wechat_runtime = WechatRuntime(auto_start=False)
            acceptors.append(self.wechat_runtime)
        elif channel_type == "stdio":
            acceptors.append(StdioSessionAcceptor())
        else:
            # config-driven 多 channel（无参）
            web_enabled = channel_enabled("channel_web")
            wechat_enabled = channel_enabled("channel_wechat")
            if web_enabled:
                listener = get_web_listener()
                acceptors.append(
                    WebSessionAcceptor(host=listener.interface, port=listener.port)
                )
                # web 存在 → 提供 console 控制（idle 或 auto_start）
                self.wechat_runtime = WechatRuntime(auto_start=wechat_enabled)
                acceptors.append(self.wechat_runtime)
            elif wechat_enabled:
                # 无 web 时 wechat standalone（config-driven）
                self.wechat_runtime = WechatRuntime(
                    auto_start=True, on_bot_exit=self._request_shutdown
                )
                acceptors.append(self.wechat_runtime)
            if not acceptors:
                # 无任何 enable 的 channel → 默认 stdio（保持旧行为）
                acceptors.append(StdioSessionAcceptor())
        return acceptors

    async def run(self, channel_type: str | None = None) -> None:
        """Gateway 主入口。

        Args:
            channel_type: "stdio" / "wechat" / "web" 单 channel（explicit flag）；
                None → 无参 config-driven 多 channel（读 plugins.channels）。
                ref: gateway.md 启动模式语义
        """
        setup_logging()
        try:
            self._profile = _ensure_profile()
        except ValueError as e:
            print(f"\n配置错误: {e}")
            return

        tasks = [await a.start(self) for a in self._build_acceptors(channel_type)]
        await self._serve(tasks)

    async def _serve(self, tasks: list[asyncio.Task]) -> None:
        """等待所有 acceptor task 结束；任一结束则带停其余（进程退出）。

        多 channel 语义：所有 channel 结束才退进程。wechat supervisor 驻留至
        gateway shutdown，故 wechat 被 stop 不会单独触发进程退出；web 结束 /
        SIGINT 时 request_shutdown → wechat supervisor 退出 → gather 完成。
        """
        loop = asyncio.get_running_loop()
        installed_signal = False
        if len(tasks) == 1 and self.wechat_runtime is not None:
            # standalone wechat：SIGINT/SIGTERM → 优雅停（无 uvicorn 兜底）
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, self._request_shutdown)
                    installed_signal = True
                except NotImplementedError:
                    pass
        try:
            if len(tasks) == 1:
                await tasks[0]
            else:
                _, pending = await asyncio.wait(
                    tasks, return_when=asyncio.FIRST_COMPLETED
                )
                self._request_shutdown()
                if pending:
                    await asyncio.wait(pending, timeout=STOP_TIMEOUT + 2.0)
                    for t in pending:
                        if not t.done():
                            t.cancel()
                            await asyncio.gather(t, return_exceptions=True)
        finally:
            if installed_signal:
                for sig in (signal.SIGINT, signal.SIGTERM):
                    try:
                        loop.remove_signal_handler(sig)
                    except (NotImplementedError, ValueError):
                        pass


def main() -> None:
    """Gateway 进程入口（被 console script `gateway` 调用）。

    用法：
        gateway                    # config-driven 多 channel（读 everlingo.yaml channels）
        gateway --channel_stdio    # 仅 Stdio Channel
        gateway --channel_wechat   # 仅 Wechat Channel（standalone）
        gateway --channel_web      # 仅 Web Channel（FastAPI + 前端）

    ref: /docs/impl-spec/gateway.md — 启动模式语义
    """
    args = _parse_args()
    _run(args)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="EverLingo Gateway")
    channel_group = parser.add_mutually_exclusive_group()
    channel_group.add_argument(
        "--channel_stdio",
        action="store_true",
        default=False,
        help="启动 Stdio Channel",
    )
    channel_group.add_argument(
        "--channel_wechat",
        action="store_true",
        default=False,
        help="启动 Wechat Channel（standalone）",
    )
    channel_group.add_argument(
        "--channel_web",
        action="store_true",
        default=False,
        help="启动 Web Channel（FastAPI + 前端）",
    )
    return parser.parse_args(argv)


def _run(args: argparse.Namespace) -> None:
    if args.channel_wechat:
        channel_type = "wechat"
    elif args.channel_web:
        channel_type = "web"
    elif args.channel_stdio:
        channel_type = "stdio"
    else:
        # 无参 → config-driven 多 channel
        channel_type = None
    gateway = Gateway()
    asyncio.run(gateway.run(channel_type=channel_type))


if __name__ == "__main__":
    main()
