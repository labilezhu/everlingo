# 应用的主入口

## gateway

/src/everlingo/gateway/gateway.py 。用户启动 gateway 。 说明见 [gateway.md](/docs/impl-spec/gateway.md)

## python module main

位于 /src/everlingo/__main__.py 。它简单调用  /src/everlingo/main.py 

src/everlingo/main.py 应该实现为与 命令入口 `gateway --channel_stdio ` 相同的效果。

