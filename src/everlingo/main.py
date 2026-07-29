# ref: app-entry.md — python module main
# everlingo 主入口。向后兼容：无子命令时 = 当前 stdio gateway 行为。
# 子命令：
#   everlingo mem ...        memory vault 搜索索引维护
#   everlingo gateway ...    显式启动 gateway 进程
#   everlingo wiki ...       wiki 知识库静态站构建与服务
#   everlingo ws_router ...  前台反代 + 认证服务（多用户部署，PR2 实现）
#   everlingo ws_master ...  后台编排服务（多用户部署，PR1 实现）

import argparse
import asyncio
import sys

from . import workspace


def _add_workspace_args(parser: argparse.ArgumentParser) -> None:
    ws_group = parser.add_mutually_exclusive_group()
    ws_group.add_argument(
        "-w",
        "--workspace",
        default=None,
        help=(
            "指定 workspace 名（位于 ~/.everlingo/workspaces/<name>/）。"
            " 默认由 EVERLINGO_WORKSPACE 环境变量决定，再回退到 'default'。"
            " 与 --workspace-dir 互斥。"
            " ref: docs/impl-spec/worksplace/workspace.md"
        ),
    )
    ws_group.add_argument(
        "--workspace-dir",
        default=None,
        help=(
            "指定 workspace 根目录的任意路径（绝对或相对）。"
            " 默认由 EVERLINGO_WORKSPACE_DIR 环境变量决定。"
            " 与 --workspace 互斥；优先级高于 --workspace。"
            " ref: docs/impl-spec/worksplace/workspace.md"
        ),
    )


def _apply_workspace_args(args: argparse.Namespace) -> None:
    """仅当 CLI 显式传入 --workspace / --workspace-dir 时覆盖默认值；
    否则由 workspace 模块自行读取环境变量或回退到 'default'。"""
    if getattr(args, "workspace_dir", None) is not None:
        workspace.init_workspace_dir(args.workspace_dir)
    elif getattr(args, "workspace", None) is not None:
        workspace.init_workspace(args.workspace)


def _add_ws_master_cli_subparsers(sub) -> None:
    """Add ws_master CLI subcommand parsers (user/pat/ws/identity)."""
    # user
    p_user = sub.add_parser("user", help="用户管理")
    user_sub = p_user.add_subparsers(dest="user_cmd", required=True)
    p_user_add = user_sub.add_parser("add", help="创建用户")
    p_user_add.add_argument("--name", required=True, help="用户名（英文字母 + 下划线）")
    p_user_add.add_argument("--display-name", required=True, help="展示名")
    p_user_add.add_argument("--password", default=None, help="密码（不指定则交互输入）")
    user_sub.add_parser("list", help="列出所有用户")
    p_user_rm = user_sub.add_parser("rm", help="删除用户")
    p_user_rm.add_argument("--name", required=True, help="用户名")
    p_user_rm.add_argument("--purge", action="store_true", help="同时 stop+remove 所有 ws-container 并删 host 目录")

    # pat
    p_pat = sub.add_parser("pat", help="PAT 管理")
    pat_sub = p_pat.add_subparsers(dest="pat_cmd", required=True)
    p_pat_add = pat_sub.add_parser("add", help="生成 PAT")
    p_pat_add.add_argument("--user", required=True, help="用户名")
    p_pat_add.add_argument("--label", required=True, help="标签")
    p_pat_add.add_argument("--expires", default=None, help="过期时间（ISO8601 或相对天数如 365d）")
    p_pat_list = pat_sub.add_parser("list", help="列出 PAT")
    p_pat_list.add_argument("--user", required=True, help="用户名")
    p_pat_rm = pat_sub.add_parser("rm", help="吊销 PAT")
    p_pat_rm.add_argument("--id", required=True, dest="pat_id", help="PAT ID")

    # ws
    p_ws = sub.add_parser("ws", help="ws-container 管理")
    ws_sub = p_ws.add_subparsers(dest="ws_cmd", required=True)
    p_ws_add = ws_sub.add_parser("add", help="新增 ws-container")
    p_ws_add.add_argument("--user", required=True, help="用户名")
    p_ws_list = ws_sub.add_parser("list", help="列出 ws-container")
    p_ws_list.add_argument("--user", default=None, help="按用户名筛选")
    p_ws_rm = ws_sub.add_parser("rm", help="删除 ws-container")
    p_ws_rm.add_argument("--id", required=True, dest="ws_id", help="ws-container ID")
    p_ws_rm.add_argument("--purge", action="store_true", help="同时 stop+remove 容器并删 host 目录")
    p_ws_start = ws_sub.add_parser("start", help="强制拉起 ws-container")
    p_ws_start.add_argument("--id", required=True, dest="ws_id", help="ws-container ID")
    p_ws_stop = ws_sub.add_parser("stop", help="强制停机 ws-container")
    p_ws_stop.add_argument("--id", required=True, dest="ws_id", help="ws-container ID")
    p_ws_default = ws_sub.add_parser("set-default", help="切换默认 ws-container")
    p_ws_default.add_argument("--id", required=True, dest="ws_id", help="ws-container ID")

    # identity
    p_identity = sub.add_parser("identity", help="外部身份管理")
    identity_sub = p_identity.add_subparsers(dest="identity_cmd", required=True)
    p_id_list = identity_sub.add_parser("list", help="列出外部身份")
    p_id_list.add_argument("--user", required=True, help="用户名")
    p_id_unlink = identity_sub.add_parser("unlink", help="解绑外部身份")
    p_id_unlink.add_argument("--id", required=True, dest="identity_id", help="identity ID")


def _add_gateway_channel_args(parser: argparse.ArgumentParser) -> None:
    """gateway 子命令的 --channel_* 参数。"""
    ch_group = parser.add_mutually_exclusive_group()
    ch_group.add_argument(
        "--channel_stdio",
        action="store_true",
        default=False,
        help="启动 Stdio Channel（默认）",
    )
    ch_group.add_argument(
        "--channel_wechat",
        action="store_true",
        default=False,
        help="启动 Wechat Channel",
    )
    ch_group.add_argument(
        "--channel_web",
        action="store_true",
        default=False,
        help="启动 Web Channel（FastAPI + 前端）",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="everlingo",
        description="EverLingo - AI 外语学习助手",
    )
    # 全局 workspace 参数：无子命令（向后兼容 stdio gateway）也支持
    _add_workspace_args(parser)
    sub = parser.add_subparsers(dest="cmd")
    # gateway 子命令
    p_gw = sub.add_parser("gateway", help="启动 Gateway 进程")
    _add_workspace_args(p_gw)
    _add_gateway_channel_args(p_gw)
    # mem 子命令
    p_mem = sub.add_parser("mem", help="memory vault 搜索索引维护")
    _add_workspace_args(p_mem)
    mem_sub = p_mem.add_subparsers(dest="mem_cmd", required=True)
    # indexer start/status
    p_idx = mem_sub.add_parser("indexer", help="indexer 进程控制")
    p_idx_sub = p_idx.add_subparsers(dest="indexer_cmd", required=True)
    p_start = p_idx_sub.add_parser("start", help="前台启动 indexer（阻塞，Ctrl-C 退出）")
    p_start.add_argument("--log-level", default="info")
    p_idx_sub.add_parser("status", help="查询 indexer 状态")
    # reindex
    p_reindex = mem_sub.add_parser("reindex", help="增量刷新或全量重建")
    p_reindex.add_argument(
        "path",
        nargs="?",
        default=None,
        help="文件或目录路径（相对 $workspace/memory/languages/$lang/vault）；省略=全 vault",
    )
    p_reindex.add_argument("--rebuild", action="store_true", help="完全删除 index，从零重建")
    p_reindex.add_argument("-v", "--verbose", action="store_true", help="逐文件输出")
    # wiki 子命令
    p_wiki = sub.add_parser("wiki", help="wiki 知识库静态站构建与服务")
    _add_workspace_args(p_wiki)
    wiki_sub = p_wiki.add_subparsers(dest="wiki_cmd", required=True)
    p_build = wiki_sub.add_parser("build", help="构建 wiki 静态站")
    _add_workspace_args(p_build)
    p_build.add_argument(
        "--dist",
        default=None,
        help="输出目录（默认 $workspace/.wiki-dist）",
    )
    p_serve = wiki_sub.add_parser("serve", help="启动 wiki web 服务（阻塞）")
    _add_workspace_args(p_serve)
    p_serve.add_argument(
        "--dist",
        default=None,
        help="构建产物目录（默认 $workspace/.wiki-dist）",
    )
    p_serve.add_argument(
        "--port",
        type=int,
        default=8765,
        help="监听端口（默认 8765）",
    )
    # ws_router 子命令（PR2 实现完整反代 + 认证逻辑）
    p_ws_router = sub.add_parser("ws_router", help="前台反代 + 认证服务（多用户部署）")
    p_ws_router.add_argument(
        "--config",
        default=None,
        help="配置文件路径（daemon 模式），如 ws_router.yaml",
    )
    # ws_master 子命令（PR1 实现完整编排 + CLI 运维逻辑）
    p_ws_master = sub.add_parser("ws_master", help="后台编排服务（多用户部署）")
    p_ws_master.add_argument(
        "--config",
        default=None,
        help="配置文件路径（daemon 模式），如 ws_master.yaml",
    )
    ws_master_sub = p_ws_master.add_subparsers(dest="ws_master_cmd")
    _add_ws_master_cli_subparsers(ws_master_sub)
    return parser


def _dispatch(args: argparse.Namespace) -> int:
    if args.cmd == "gateway":
        # 显式 gateway 子命令
        _apply_workspace_args(args)
        from .gateway.gateway import _run as gw_run

        gw_run(args)
        return 0
    if args.cmd == "mem":
        _apply_workspace_args(args)
        if args.mem_cmd == "indexer":
            from .mem.vault.search.cli import cmd_indexer_start, cmd_indexer_status

            if args.indexer_cmd == "start":
                return cmd_indexer_start(args)
            if args.indexer_cmd == "status":
                return cmd_indexer_status(args)
        if args.mem_cmd == "reindex":
            from .mem.vault.search.cli import cmd_reindex

            return cmd_reindex(args)
        return 2
    if args.cmd == "wiki":
        _apply_workspace_args(args)
        if args.wiki_cmd == "build":
            from .wiki.cli import cmd_build

            return cmd_build(args)
        if args.wiki_cmd == "serve":
            from .wiki.cli import cmd_serve

            return cmd_serve(args)
        return 2
    if args.cmd == "ws_router":
        if args.config:
            from .ws_router.app import run_daemon

            run_daemon(args.config)
            return 0
        print(
            "WS-Router: use `everlingo ws_router --config ws_router.yaml` for daemon mode.",
            file=sys.stderr,
        )
        return 0
    if args.cmd == "ws_master":
        # PR1 实现完整编排 + CLI 运维逻辑
        if args.ws_master_cmd:
            # CLI 模式（user/pat/ws/identity），--config 仅用于定位 sqlite
            from .ws_master.cli import dispatch

            return dispatch(args)
        if args.config:
            # Daemon 模式
            from .ws_master.app import run_daemon

            run_daemon(args.config)
            return 0
        # 无子命令且无 --config，显示帮助
        print(
            "WS-Master: use `everlingo ws_master --config ws_master.yaml` for daemon mode,\n"
            "or `everlingo ws_master user add/list ...` for CLI mode.",
            file=sys.stderr,
        )
        return 0
    # 无子命令：向后兼容 = stdio gateway
    _apply_workspace_args(args)
    from .gateway.gateway import Gateway

    gateway = Gateway()
    asyncio.run(gateway.run(channel_type="stdio"))
    return 0


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    rc = _dispatch(args)
    if rc is not None and rc != 0:
        sys.exit(rc)


if __name__ == "__main__":
    main()
