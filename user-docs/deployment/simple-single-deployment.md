# Simple Single Instance Deployment

##  Deployment mode 1 - Single Instance for Local Access

Notice: Plain Text HTTP for local network access

```bash
export HOST_WS_DIR=<your path to save workspace>
export OPENAI_API_KEY=<your key>
export base_url_for_browser=http://your_host_ip:8000
export OPENAI_BASE_URL=https://openrouter.ai/api/v1
export OPENAI_MODEL=deepseek/deepseek-v4-flash
export OPENAI_EMBEDDING_MODEL=baai/bge-m3
export target_language=en

export EVERLINGO_VER=0.1.0-rc.13

# 宿主侧多用户隔离的目录命名（与容器内 os_user 无关）


# 整目录挂载覆盖 default workspace
# rm -rf ${HOST_WS_DIR}
mkdir -p ${HOST_WS_DIR}
cd $HOST_WS_DIR

cat >${HOST_WS_DIR}/everlingo.yaml << EOF
sys_setting:
  openai_api_key: "$OPENAI_API_KEY"
  openai_base_url: $OPENAI_BASE_URL
  openai_model: $OPENAI_MODEL
  openai_embedding_model: $OPENAI_EMBEDDING_MODEL
  logging_setting:
    log_file: ''
    log_level: debug
user_profile:
  language:
    interface_language: zh-CN #默认界面语言是中文
    target_language: ${target_language} #默认目标学习语言是英文

plugins:
  channels:
    channel_web: # Web Session Acceptor 配置
      listener: # 监听地址
        port: 8000 # 默认 8000
        interface: 0.0.0.0  # 默认 localhost
      public_address: # 浏览器访问地址。如外网或 https 反向代理访问时配置
        base_url: $base_url_for_browser
EOF

image=ghcr.io/labilezhu/everlingo:${EVERLINGO_VER}
docker run --rm -d \
  -p 8000:8000 \
  -v ${HOST_WS_DIR}:/home/everlingo/.everlingo/workspaces/default \
  --name everlingo -h everlingo \
  ${image}


tail -f ${HOST_WS_DIR}/logs/*
```
