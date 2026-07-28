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

## edge

多用户部署拓扑中的前台反代 + 认证服务。位于 `src/everlingo/edge/`，入口 `python -m everlingo edge --config edge.yaml`。说明见 [edge.md](/docs/impl-spec/multiple-users/edge.md)。

```bash
# 启动 Edge（监听 8100，经 nginx 反代对外）
everlingo edge --config edge.yaml
```

edge 是独立进程，与 gateway 平级；面向公网（经 nginx），负责认证与按 user_id 反代到对应用户容器。仅在「Master 编排模式」下使用（见 [deploy.md](/docs/impl-spec/multiple-users/deploy.md)）。

## master

多用户部署拓扑中的后台编排服务。位于 `src/everlingo/master/`，入口 `python -m everlingo master --config everlingo_master.yaml`。说明见 [everlingo-master.md](/docs/impl-spec/multiple-users/everlingo-master.md)。

```bash
# 启动 Master daemon（仅在 everlingo-net 内监听 8101）
everlingo master --config everlingo_master.yaml

# CLI 运维（直连 sqlite，不经过 daemon）
everlingo master user add --name mark --display-name "Mark"
everlingo master pat add --user mark --label "curl-laptop"
everlingo master container list
```

master 是独立进程，与 gateway 平级；不对公网暴露，负责用户容器 create/start/stop/remove 与 user→backend 解析。仅在「Master 编排模式」下使用。

