# ref: docs/impl-spec/workspace-console/ws-console-arch.md — WechatRuntime in-process 托管
# wechat 状态机（WechatAdminState）+ 单例锁（acquire_lock）+ WechatRuntime（runtime.py）。
# in-process 后无 UDS admin server（原 server.py 已删），router 直接读 state.snapshot()。
