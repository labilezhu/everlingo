# Pending Bugs

## 已修复

### 1. Bind mount source 路径错用容器内路径（2026-07-29）

**现象**：`docker inspect everlingo-mark-2738e7bc` 显示 `"/workspaces/mark/2738e7bc:/home/everlingo/.everlingo/workspaces/default"`，bind source `/workspaces/mark/2738e7bc` 是 ws-master 容器内路径而非宿主路径，docker daemon 无法绑定到正确的宿主目录，且 ws-master 写的 `everlingo.yaml` 模板不落在 bind source 下。

**根因**：`host_ws_dir` 一条路径被同时用于"容器内文件操作"和"docker daemon bind source"两个不同语义，容器化时两者不同。

**修复**：新增配置字段 `container_ws_dir`，用 `host_to_container_ws_path()` 做前缀转换，分离两路径职责。详见 [TASKS.md](/TASKS.md) 对应条目。

**存量清理**：旧 DB 中 `host_workspace_dir="/workspaces/mark/..."` 记录需 `user rm --purge` 或删 sqlite 重建。

---

## 未修复



---

