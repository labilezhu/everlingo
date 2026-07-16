# 应用的主入口

## gateway

/src/everlingo/gateway/gateway.py 。用户启动 gateway 。 说明见 [gateway.md](/docs/impl-spec/gateway.md)

## python module main

位于 /src/everlingo/__main__.py 。它简单调用  /src/everlingo/main.py 

src/everlingo/main.py 应该实现为与 命令入口 `gateway --channel_stdio ` 相同的效果。

## wiki

位于 `/src/everlingo/wiki/cli.py` 。把 [Memory Vault](/src/everlingo/mem/vault/vault_specs/default/vault_spec.md) 渲染成可浏览的静态网站。说明见 [wiki-spec.md](/docs/impl-spec/wiki/wiki-spec.md)

```bash
# 构建静态站点到 $workspace/.wiki-dist/
everlingo wiki build

# 启动本地 web server 服务构建产物（默认端口 8765）
everlingo wiki serve
```

wiki 是独立进程，不通过 `gateway --channel_*` 启动，与 gateway 平级。

