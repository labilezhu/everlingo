# 应用的主入口

## gateway

/src/everlingo/gateway/gateway.py 。用户启动 gateway 。 说明见 [gateway.md](/docs/impl-spec/gateway.md)

## python module main

位于 /src/everlingo/__main__.py 。它简单调用  /src/everlingo/main.py 

src/everlingo/main.py 应该实现为与 命令入口 `gateway --channel_stdio ` 相同的效果。

## wiki

位于 `/src/everlingo/wiki/cli.py` 。把 [Memory Vault](/src/everlingo/mem/vault/templates/default/spec/vault_spec.md) 渲染成可浏览的静态网站。说明见 [wiki-spec.md](/docs/impl-spec/wiki/wiki-spec.md)

```bash
# 构建静态站点到 $workspace/.wiki-dist/
everlingo wiki build

# 启动本地 web server 服务构建产物（默认端口 8765）
everlingo wiki serve
```

wiki 是独立进程，不通过 `gateway --channel_*` 启动，与 gateway 平级。

## ws_router

多用户部署拓扑中的前台反代 + 认证服务（原 `edge`，重命名为 `ws_router` — workspace container router）。位于 `src/everlingo/ws_router/`，入口 `python -m everlingo ws_router --config ws_router.yaml`。说明见 [ws-router.md](/docs/impl-spec/multiple-users/ws-router.md)。

```bash
# 启动 WS-Router（监听 8100，经 nginx 反代对外）
everlingo ws_router --config ws_router.yaml
```

ws_router 是独立进程，与 gateway 平级；面向公网（经 nginx），负责认证与按 user_id 反代到对应 workspace container。仅在「WS-Master 编排模式」下使用（见 [deploy.md](/docs/impl-spec/multiple-users/deploy.md)）。

## ws_master

多用户部署拓扑中的后台编排服务（原 `master`，重命名为 `ws_master` — workspace container master）。位于 `src/everlingo/ws_master/`，入口 `python -m everlingo ws_master --config ws_master.yaml`。说明见 [ws-master.md](/docs/impl-spec/multiple-users/ws-master.md)。

```bash
# 启动 WS-Master daemon（仅在 everlingo-net 内监听 8101）
everlingo ws_master --config ws_master.yaml

# CLI 运维（直连 sqlite，不经过 daemon）
everlingo ws_master user add --name mark --display-name "Mark"
everlingo ws_master pat add --user mark --label "curl-laptop"
everlingo ws_master ws list
```

ws_master 是独立进程，与 gateway 平级；不对公网暴露，负责 workspace container create/start/stop/remove 与 user→backend 解析。仅在「WS-Master 编排模式」下使用。

