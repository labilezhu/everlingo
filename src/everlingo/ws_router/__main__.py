# WS-Router 模块入口（PR0 骨架占位）
# 完整实现在 PR2，当前仅占位。
# 正式入口通过 `everlingo ws_router --config ws_router.yaml` 调用。

import sys


def main() -> None:
    print(
        "WS-Router: not yet implemented (PR2). "
        "Use `everlingo ws_router --help` for usage.",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()