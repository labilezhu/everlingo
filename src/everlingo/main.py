# ref: app-entry.md — python module main
# everlingo 主入口。向后兼容：无子命令时 = 当前 stdio gateway 行为。
# 子命令：
#   everlingo mem ...     memory vault 搜索索引维护
#   everlingo gateway ... 显式启动 gateway 进程

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
        help="文件或目录路径（相对 $workspace/memory）；省略=全 vault",
    )
    p_reindex.add_argument("--rebuild", action="store_true", help="完全删除 index，从零重建")
    p_reindex.add_argument("-v", "--verbose", action="store_true", help="逐文件输出")
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
