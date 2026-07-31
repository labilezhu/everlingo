# ref: docs/impl-spec/workspace-console/architecture.md — wechat admin server
# wechat gateway 进程内：admin 状态机 + 单例锁 + UDS admin server。
# 仅 --channel_wechat 进程加载；--channel_web 进程经 socket 通信，不 import。
