# ref: gateway.md — Gateway 进程入口
# ref: app-entry.md — 应用主入口
# ref: docs/impl-spec/memory-extract-agent-spec.md — 异步执行
# ref: docs/impl-spec/memory-writer-agent-spec.md — 异步执行（Writer 单例）

import argparse
import asyncio
import logging

from ..log_utils import setup_logging
from ..models import LANGUAGES, UserProfile
from ..setting import load_profile, save_profile
from .session_acceptor import StdioSessionAcceptor, WechatSessionAcceptor
from .web_acceptor import WebSessionAcceptor
from .session import Session


logger = logging.getLogger(__name__)


# ── Memory Writer Agent 单例（进程级）───────────────────────────────
# ref: memory-writer-agent-spec.md — 进程级单例，独立 daemon Thread + queue.Queue。
# Memory Extract Agent 通过 enqueue(entries) 把已生成 entries 转交给 Writer；
# Writer 异步消费、写入 memory vault。
#
# 延迟导入避免 gateway -> mem_writer_agent -> llm -> ... -> gateway 循环。
# Extract Agent 已通过 EntryWriterProtocol.enqueue 转发；本模块只需要暴露单例。

memory_writer: "_MemoryWriterProxy"  # type: ignore[type-arg]


class _MemoryWriterProxy:
    """延迟构造的 Writer 单例代理。

    实际 MemoryWriterAgent 在首次访问时构造并 start()。
    这样既能保留「gateway 模块级实例」的单例语义，
    又能在测试中替换为 mock（patch / 直接赋值）。
    """

    def __init__(self) -> None:
        self._agent: object | None = None

    def _ensure(self):
        if self._agent is None:
            from ..mem.agents.mem_writer_agent import MemoryWriterAgent
            self._agent = MemoryWriterAgent()
            self._agent.start()
            logger.info("memory_writer started")
        return self._agent

    def enqueue(self, entries) -> None:
        self._ensure().enqueue(entries)


memory_writer = _MemoryWriterProxy()


# ── Search Client 单例（进程级）───────────────────────────────────
# ref: docs/impl-spec/search/memory-vault-search-spec.md — gateway 侧接口
# gateway 进程持有一个 SearchClient 单例；Writer 写完 .md 后通过
# mem_writer_tools._post_write_hook 触发 index_file(path) fire-and-forget。
# indexer 不可达时 SearchClient.search() / index_file() 自身降级。

search_client: "SearchClient"  # type: ignore[type-arg]


class _SearchClientProxy:
    """延迟构造的 SearchClient 代理；indexer 不可达时方法返回 []/False。"""

    def __init__(self) -> None:
        self._client: object | None = None

    def _ensure(self):
        if self._client is None:
            from ..mem.vault.search.client import SearchClient
            from .. import workspace

            self._client = SearchClient(workspace.indexer_socket_path())
            # 安装 Writer 写后钩子：每次 mem_* 写/删都 fire-and-forget 投递索引
            from ..mem.agents import mem_writer_tools

            def _hook(rel: str, op: str) -> None:
                if op == "delete":
                    self._client.delete_file(rel)  # type: ignore[union-attr]
                else:
                    self._client.index_file(rel)  # type: ignore[union-attr]

            mem_writer_tools.set_post_write_hook(_hook)
            logger.info("search_client initialized, post-write hook installed")
        return self._client

    def __getattr__(self, name: str):
        return getattr(self._ensure(), name)


search_client = _SearchClientProxy()


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
            session = Session(channel=channel, profile=self._profile, id=session_id)
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
    """Gateway 进程入口（被 console script `gateway` 调用）。

    用法：
        gateway --channel_stdio   # 启动 Stdio Channel（默认）
        gateway                   # 同上，默认启动 Stdio Channel
        gateway --channel_wechat  # 启动 Wechat Channel
        gateway --channel_web     # 启动 Web Channel（FastAPI + 前端）

    ref: /docs/impl-spec/gateway.md
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
    return parser.parse_args(argv)


def _run(args: argparse.Namespace) -> None:
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
