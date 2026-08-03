# Pending Bugs


## 未修复

按
mark-specific/local-deploy/130_deploy/router-master@container/router-master@container.md
部署的 [Web Chatbot](docs/impl-spec/web-chatbot.md) 用户聊天中要求找笔记，笔记是找对了，但消息中的 markdown url link 变成了：

```
https://mydomain.com:6457/mydomain.com:6457/editor?lang=en&path=items%2Fvocab%2Fdocker.md
```

重复了前缀 mydomain.com:6457


---

## 已修复

### 1. Bind mount source 路径错用容器内路径（2026-07-29）

**现象**：`docker inspect everlingo-mark-2738e7bc` 显示 `"/workspaces/mark/2738e7bc:/home/everlingo/.everlingo/workspaces/default"`，bind source `/workspaces/mark/2738e7bc` 是 ws-master 容器内路径而非宿主路径，docker daemon 无法绑定到正确的宿主目录，且 ws-master 写的 `everlingo.yaml` 模板不落在 bind source 下。

**根因**：`host_ws_dir` 一条路径被同时用于"容器内文件操作"和"docker daemon bind source"两个不同语义，容器化时两者不同。

**修复**：新增配置字段 `container_ws_dir`，用 `host_to_container_ws_path()` 做前缀转换，分离两路径职责。详见 [TASKS.md](/TASKS.md) 对应条目。

**存量清理**：旧 DB 中 `host_workspace_dir="/workspaces/mark/..."` 记录需 `user rm --purge` 或删 sqlite 重建。

---



