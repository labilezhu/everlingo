# ref: app-entry.md — python module main
# 与命令入口 `gateway --channel_stdio` 效果相同

import asyncio


def main() -> None:
    from .gateway.gateway import Gateway

    gateway = Gateway()
    asyncio.run(gateway.run(channel_type="stdio"))


if __name__ == "__main__":
    main()
