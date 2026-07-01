# ref: app-entry.md — python module main
# 与命令入口 `gateway --channel_stdio` 效果相同

import argparse
import asyncio


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="everlingo",
        description="EverLingo - AI 外语学习助手",
    )
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
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    # 仅当 CLI 显式传入 --workspace / --workspace-dir 时覆盖默认值；
    # 否则由 workspace 模块自行读取环境变量或回退到 'default'。
    # ref: docs/impl-spec/worksplace/workspace.md — 选择机制
    if args.workspace_dir is not None:
        from . import workspace

        workspace.init_workspace_dir(args.workspace_dir)
    elif args.workspace is not None:
        from . import workspace

        workspace.init_workspace(args.workspace)

    from .gateway.gateway import Gateway

    gateway = Gateway()
    asyncio.run(gateway.run(channel_type="stdio"))


if __name__ == "__main__":
    main()
