# WS-Master 模块入口（PR0 骨架占位）
# 完整实现在 PR1，当前仅占位。
# 正式入口通过 `everlingo ws_master <subcommand>` 调用。

import sys


def main() -> None:
    print(
        "WS-Master: not yet implemented (PR1). "
        "Use `everlingo ws_master --help` for usage.",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()