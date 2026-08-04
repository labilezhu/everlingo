# Simple Single Instance Deployment

当前支持 amd64(Linux/Windows WSL PC) 与 arm64( M系列的 MacOS 下的 Linux 容器 / Raspberry Pi )

其中，我已经实测的是 amd64 Linux / arm64 Raspberry Pi 。

##  Deployment mode 1 - Single Instance for Local Access

Notice: Plain Text HTTP for local network access

```bash
export HOST_WS_DIR=<your path to save workspace>

export OPENAI_API_KEY=<your key>
export OPENAI_BASE_URL=https://openrouter.ai/api/v1 # 兼容 OpenAI API 的 base URL
export OPENAI_MODEL=deepseek/deepseek-v4-flash # LLM
export OPENAI_EMBEDDING_MODEL=baai/bge-m3 # 语义搜索用的模型

export EVERLINGO_PUBLIC_BASE_URL=http://your_host_ip:8000 # 能连接到将运行的 EverLingo 的地址。用于聊天消息中的笔记超链。
export target_language=en # 目标学习语言： en/ja/zh-CN/fr/de

export EVERLINGO_VER=0.1.1-rc.3

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
        base_url: $EVERLINGO_PUBLIC_BASE_URL
EOF

WORKSPLACE_IMAGE=ghcr.io/labilezhu/everlingo:${EVERLINGO_VER}
docker run --rm -d \
  -p 8000:8000 \
  -v ${HOST_WS_DIR}:/home/everlingo/.everlingo/workspaces/default \
  --name everlingo -h everlingo \
  ${WORKSPLACE_IMAGE}
```

成功后，访问网址：
http://your_host_ip:8000