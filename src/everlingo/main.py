# ref: app-entry.md — python module main
# 与命令入口 `gateway --channel_stdio` 效果相同

import argparse
import asyncio


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="everlingo",
        description="EverLingo - AI 外语学习助手",
    )
    parser.add_argument(
        "-w",
        "--workspace",
        default=None,
        help=(
            "指定 workspace 名（位于 ~/.everlingo/workspaces/<name>/）。"
            " 默认由 EVERLINGO_WORKSPACE 环境变量决定，再回退到 'default'。"
            " ref: docs/impl-spec/worksplace/workspace.md"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    # 仅当 CLI 显式传入 --workspace 时覆盖默认值；否则由 workspace 模块
    # 自行读取 EVERLINGO_WORKSPACE 环境变量或回退到 'default'。
    # ref: docs/impl-spec/worksplace/workspace.md — 选择机制
    if args.workspace is not None:
        from . import workspace

        workspace.init_workspace(args.workspace)

    from .gateway.gateway import Gateway

    gateway = Gateway()
    asyncio.run(gateway.run(channel_type="stdio"))


if __name__ == "__main__":
    main()