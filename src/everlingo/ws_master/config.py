"""WS-Master 配置加载。

从 ws_master.yaml 加载配置，支持 env 展开 `${VAR}`。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from everlingo.utils.yaml_env import expand_env_vars


@dataclass
class MasterConfig:
    """WS-Master 配置，对应 ws_master.yaml 的 `master:` 节。"""

    listen: str = "0.0.0.0:8101"
    shared_secret: str = ""
    db: str = "/root/.everlingo/ws_master.sqlite"
    host_ws_dir: str = "/workspaces"
    container_ws_dir: str = "/workspaces"

    image: str = "ghcr.io/labilezhu/everlingo:0.0.1-rc.3"
    network: str = "everlingo-net"
    ws_template: str = "/etc/everlingo/ws_container_everlingo_template.yaml"

    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = ""
    openai_embedding_model: str = ""

    # 外部访问地址（如 https://app.everlingo.com）：注入 ws-container env
    # EVERLINGO_PUBLIC_BASE_URL，供 ws-container 内 setting.get_web_public_base_url()
    # env fallback 使用——Chat Agent 据此生成指向外部域名的笔记链接
    # （Web Chatbot / Chrome Extension 均依赖）。
    # 应与 ws_router.yaml 的 public_base_url 保持一致。
    public_base_url: str = ""

    idle_timeout: int = 0
    healthcheck_interval: int = 60
    readiness_timeout: int = 60
    max_ws_per_user: int = 1

    @classmethod
    def load(cls, path: str | Path) -> "MasterConfig":
        """Load config from YAML file, expanding env vars in LLM fields."""
        path = Path(path)
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        master = raw.get("master", {}) if isinstance(raw, dict) else {}

        # Expand ${VAR} / $VAR env references for all string fields
        master = expand_env_vars(master)

        # Validate public_base_url scheme if non-empty
        pbu = master.get("public_base_url", "")
        if isinstance(pbu, str) and pbu.strip():
            pbu = pbu.strip().rstrip("/")
            if not re.match(r"^https?://", pbu):
                raise ValueError(
                    f"master.public_base_url must start with http:// or https://, "
                    f"got: {pbu!r}"
                )
            master["public_base_url"] = pbu

        return cls(**{k: v for k, v in master.items() if k in cls.__dataclass_fields__})


def host_to_container_ws_path(host_workspace_dir: str, config: MasterConfig) -> Path:
    """Translate a host-side workspace path to the ws-master container path.

    Given a host path like ``<host_ws_dir>/<user>/<id>``, returns the equivalent
    path under ``config.container_ws_dir``. This is used when the ws-master
    container needs to perform file operations (mkdir, copy template, rmtree)
    on a directory that the docker daemon accesses via the host path.

    Raises ``ValueError`` if ``host_workspace_dir`` is not under ``config.host_ws_dir``.
    """
    rel = Path(host_workspace_dir).relative_to(config.host_ws_dir)
    return Path(config.container_ws_dir) / rel