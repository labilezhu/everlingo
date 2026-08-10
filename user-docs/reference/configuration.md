# 配置参考

## Environment Variables
以下列出使用的环境变量。应用通过 [python-dotenv](https://github.com/theskumar/python-dotenv) 加载 `.env` 文件，
也可以通过 shell 环境变量直接注入。

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OPENAI_API_KEY` |  | LLM Provider API Key（必需） |
| `OPENAI_BASE_URL` |  | 兼容 OpenAI Chat Completions 的 API Base URL |
| `OPENAI_MODEL` |  | 使用的模型名称 |




## 配置文件 - EverLingoSetting
以下列出配置文件的信息。

配置文件位置： `$workspace/everlingo.yaml` 。 配置文件使用 yaml 格式。

**yaml 结构如下。必须按照这个结构去实现**
```yaml
sys_setting:
  openai_api_key:
  openai_base_url: 
  openai_model: 
  openai_embedding_model:
  logging_setting:
  tracing_setting:
user_profile:
git_backup:                          # Memory Vault 版本控制与远端备份（可选）
  enabled: false
  remote_url:
  branch: main
  auth:
    method: ssh
    ssh_private_key_file:
    pat:
  commit_interval: 300
  push_interval: 300
plugins:
  channels:
    channel_web:
      listener:
        interface: localhost
        port: 8000
      public_address:
        base_url:
    channel_wechat:
      enable: false
```

配置文件包括以下子小节的内容。

在代码中， class 名称叫 `EverLingoSetting`. 


### 系统设定 - SysSetting

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `openai_api_key` |  | LLM Provider API Key（必需） |
| `openai_base_url` |  | 兼容 OpenAI Chat Completions 的 API Base URL |
| `openai_model` |  | 使用的模型名称 |

配置文件的配置项目的优先级高于 Environment Variables 。 即如果一个语义相同的配置项，在配置文件和 Environment Variables 中均配置了，优先使用 配置文件的配置项 。

在代码中， class 名称叫 `SysSetting`.

#### 日志设定 - LoggingSetting

| 变量        | 默认值                          | 说明                                                  |
| ----------- | ------------------------------- | ----------------------------------------------------- |
| `log_file`  | $workspace/logs/everlingo.log | 日志文件路径                                          |
| `log_level` | debug                           | 日志文件中的日志输出级别。可选：debug/info/warn/error |



#### 跟踪设定 - Tracing

| 变量                  | 默认值 | 说明                                              |
| --------------------- | ------ | ------------------------------------------------- |
| `tracing_service`     |        | 可选： langfuse  。空值时不启动任何 tracing       |
| `langfuse_secret_key` |        | langfuse secret key。如 sk-lf-xxxx                |
| `langfuse_public_key` |        | langfuse public key。如 pk-lf-ce-xxxx             |
| `langfuse_base_url`   |        | langfuse base url 。如 http://192.168.16.130:3300 |



### 用户 Profile - UserProfile

首次运行时交互生成，之后自动加载。

配置项参考 [DOMAIN.md](/DOMAIN.md) 中 `用户 Profile` 一节。

- `interface_language`（界面语言）：**可选**。留空时运行时按 OS locale 推断、兜底 `en`；非空时必须在可用界面语言内（当前 `zh-CN` / `en`）。推断值不写回 yaml。
- `target_language`（目标学习语言）：必选。

在代码中， class 名称叫 `UserProfile`. 

### 用户自由偏好笔记 - USER.md

存放位置： `$workspace/memory/USER.md` ，Markdown 自由文本。

参考 [DOMAIN.md](/DOMAIN.md) 中 `用户自由偏好笔记 - USER.md` 一节。

可通过与 Agent 聊天让 Agent 调用 `user_doc` 工具更新，也可用外部编辑器直接编辑。


### Memory Vault 版本控制与远端备份 - GitBackup

存放位置：配置于 `$workspace/everlingo.yaml` 的 `git_backup` 段。把 `$workspace/memory` 当作一个 git repo，提供本地版本历史 + 远端备份（异机恢复）。详情见 [vault-version-control.md](/docs/impl-spec/worksplace/vault-version-control.md)。

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `enabled` | `false` | 是否启用自动 commit + 自动 push |
| `remote_url` | `""` | 任意 git remote，如 `git@github.com:user/vault.git` |
| `branch` | `main` | 上游分支 |
| `auth.method` | `ssh` | 凭证模式：`ssh` / `https_pat` / `https_none` |
| `auth.ssh_private_key_file` | `""` | ssh 模式私钥路径；空=用系统 `~/.ssh/` |
| `auth.pat` | `""` | https_pat 模式：GitHub fine-grained PAT（contents:write） |
| `commit_interval` | `300` | 自动 commit 去抖秒 |
| `push_interval` | `300` | 自动 push 间隔秒；0=仅手动触发 |

凭证随 `everlingo.yaml` 落盘（文件 0600 权限保护）；不使用系统 keychain（容器内不可用）；ws-master 不参与版本控制。


### 插件配置 - Plugins

插件配置，包含通道插件等。

在代码中， class 名称叫 `Plugins`。

#### Web 通道配置 - ChannelWeb

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `listener.interface` | `localhost` | Web 监听接口。如需要 LAN/外网访问，设为 `0.0.0.0` |
| `listener.port` | `8000` | Web 监听端口 |
| `public_address.base_url` | `http://{interface}:{port}` | 浏览器访问地址。空值时由 listener 生效配置自动生成。外网或 https 反向代理时需显式设置 |

代码中 class 名称叫 `ChannelWeb`。

#### Wechat 通道配置 - ChannelWechat

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `enable` | `false` | 是否启用 wechat channel。`true` 时 gateway 无参启动会自动 in-process 启动 wechat；`false` 或节点不存在则不启动。用户首次经 web console 登录成功后自动写 `true`，用户主动停止后写 `false` |

代码中 class 名称叫 `ChannelWechat`。详见 [workspace-console/ws-console-arch.md](/docs/impl-spec/workspace-console/ws-console-arch.md)。
