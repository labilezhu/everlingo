"""WS-Router 模块入口。

python -m everlingo.ws_router --config ws_router.yaml  → daemon 模式（FastAPI）
通常通过 `everlingo ws_router --config ws_router.yaml` 子命令调用。
"""

import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--config":
        from .app import run_daemon

        run_daemon(sys.argv[2])
    else:
        print("WS-Router: use `everlingo ws_router --config ws_router.yaml` for daemon mode.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
