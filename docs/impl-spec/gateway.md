# Gateway 服务

一个独立的 python 进程。


负责：


启动时，检查用户个性初始化的`必选设置`:
- 界面语言
- 目标学习语言
如果未设置，设置为以下默认值：
- 界面语言 = zh-CN
- 目标学习语言 = en


进程入口 `/src/everlingo/gateway/gateway.py` 。 进程提供命令行参数：
```bash
# 启动 Stdio Channel
gateway --channel_stdio

# 默认启动 Stdio Channel
gateway

# 启动 Wechat Channel。
gateway --channel_wechat
```

## Session

见 [Session](/docs/impl-spec/session.md)
