# WS-Master 模块入口
#
# 两种模式：
#   python -m everlingo.ws_master --config ws_master.yaml  → daemon 模式（FastAPI）
#   python -m everlingo.ws_master user add ...             → CLI 模式（直连 sqlite）
#
# 通常通过 `everlingo ws_master` 子命令调用，入口在 everlingo/main.py。

import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--config":
        from .app import run_daemon

        run_daemon(sys.argv[2])
    elif len(sys.argv) > 1:
        from .cli import main as cli_main

        cli_main()
    else:
        print("WS-Master: use `everlingo ws_master --help` for usage.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()