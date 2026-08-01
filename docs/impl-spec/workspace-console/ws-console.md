# Workspace Console

Web UI 模块，为用户提供「工作台」视角的管理界面。与 [Web Gateway](../web-session-acceptor.md) 共用同一 8000 HTTP server（web acceptor），不另起进程。

## 定位

Workspace Console 不是聊天界面，而是**面向本机部署的运维/管理控制台**：在 web 进程内 in-process 管理 channel 实例、展示 channel 运行状态、引导 channel 登录流程。面向单用户本地场景，默认 `interface=localhost`；公网暴露不在本期范围。

> 2026-07 设计变更：原计划让 wechat gateway 跑在独立子进程、web 经 UDS admin socket 管理。经评估，子进程模型维护成本超过收益，改为 **web 进程内 in-process 托管**（`WechatRuntime` 实现 `SessionAcceptor`）。配合 `everlingo.yaml` 的 `channel_wechat.enable` 配置实现重启后自动恢复。详见 [ws-console-arch.md §1.1](./ws-console-arch.md)。

## 模块组织

首个子模块是 **channels admin**，其下第一个功能是 **wechat channel admin**：

```
Workspace Console
└── channels admin
    └── wechat channel admin
        ├── wechat channel 实例生命周期管理（启动 / 停止，in-process）
        ├── channel 运行状态展示
        ├── 微信扫码登录引导（QR-Code 网页 + 登录过程反馈）
        └── enable 持久化（登录成功写 enable=true，停止写 false，重启自动恢复）
```

## 页面导航

入口挂在 [Standalone Web Chatbot](../web-chatbot.md) header 上：

```
Standalone Web Chatbot  ──[Me]──►  /console/me  ──[Workspace Console]──►  /console/web-console
                                                                              │
                                                  channels admin ◄──────────┘
                                                                              │
                                                  wechat channel admin ◄─────┘
```

- `Me` 按钮：在 chatbot header「笔记编辑器」按钮右侧（[web-chatbot.md §Header](../web-chatbot.md)），点击 `window.location.href = '/console/me'`。
- `/console/me` 页：本期仅一个「Workspace Console」入口按钮（预留扩展位）。
- `/console/web-console`：console 首页，列出 channels admin 下各子项。
- `/console/web-console/plugins/channels/wechat_channel/admin`：wechat channel admin 页。

## 文档索引

| 文档 | 内容 |
|---|---|
| [ws-console-arch.md](./ws-console-arch.md) | 架构设计：进程拓扑、状态机、IPC 协议、生命周期管理、前端结构 |
| [phased-impl.md](./phased-impl.md) | 分阶段实施计划：阶段划分、每阶段交付物、验证方式 |

## 设计依据

- 进程拓扑与 IPC 复用 [memory-vault-search-spec.md](../search/memory-vault-search-spec.md) 的「HTTP over UDS + FastAPI/uvicorn」范式。
- Wechat channel 实现见 [channel-wechat-ilink.md](../channel-wechat-ilink.md)、`src/everlingo/gateway/channels/wechat_channel.py`。
- 前端技术栈与构建遵循 [web-chatbot.md §前端技术选型](../web-chatbot.md)（Vite + React + TailwindCSS + shadcn/ui），多入口构建沿用 `/editor` 模式。
