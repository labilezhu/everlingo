# Image 设计规范

## base image
docker image: `python:3.12.13-bookworm`

Dockerfile: docs/impl-spec/deploy/image/Dockerfile

## Linux 主用户
username: everlingo
UID & GID: 1000

权限： 可以运行 sudo 。 可以 sudo apt 安装包。

## app files
把 docs/impl-spec/deploy/image/root 目录下的目录结构和文件写入 image 的 / 下

## image 进程

启动两个进程：
```bash
uv run python -m everlingo mem indexer start &
uv run python -m everlingo.gateway.gateway --channel_web &
```

## image expose port
8000, 9000(备用)

## 经典部署方法

```bash
app_user_name=mark

os_user_name=everlingo
image=everlingo:v0.1

host_workspace=~/everlingo_workspaces/${app_user_name}
mkdir -p ${host_workspace}

#cid=$(docker create ${image})
#docker cp "$cid":/home/everlingo/.everlingo/workspaces/default/everlingo.yaml ${host_workspace}/
#docker rm "$cid"

# 查看配置示例
docker run --rm $image cat /home/everlingo/.everlingo/workspaces/default/everlingo.yaml

cat >${host_workspace}/everlingo.yaml <<"EOF"
sys_setting:
  openai_api_key: 'sk-or-v1-xyz'
  openai_base_url: 'https://openrouter.ai/api/v1'
  openai_model: 'deepseek/deepseek-v4-flash'
  openai_embedding_model: 'baai/bge-m3'
  logging_setting:
    log_file: ''
    log_level: debug
user_profile:
  language:
    interface_language: zh-CN #默认界面语言是中文
    target_language: en #默认目标学习语言是英文

plugins:
  channels:
    channel_web: # Web Session Acceptor 配置
      listener: # 监听地址
        port: 8000 # 默认 8000
        interface: 0.0.0.0  # 默认 localhost
      public_address: # 浏览器访问地址。如外网或 https 反向代理访问时配置
        base_url: https://$your_domain:$your_port
EOF

# override default workspace directory
docker run -d everlingo:v0.1 -v ${host_workspace}:/home/${os_user_name}/.everlingo/workspaces/default
```
