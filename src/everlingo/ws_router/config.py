"""WS-Router 配置加载。

从 ws_router.yaml 加载配置，支持 env 展开 `${VAR}`。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class RouterConfig:
    """WS-Router 配置，对应 ws_router.yaml 的 `ws_router:` 节。"""

    listen: str = "0.0.0.0:8100"
    base_url: str = "http://localhost:8100"
    trusted_proxy: str = "127.0.0.1"

    master_url: str = "http://ws_master:8101"
    master_secret: str = ""

    jwt_secret: str = ""
    session_ttl: int = 28800
    backend_cache_ttl: int = 60
    pat_verify_cache_ttl: int = 30

    cors_allow_origins: list[str] = field(default_factory=list)

    auth_providers: list[str] = field(default_factory=lambda: ["password"])

    @classmethod
    def load(cls, path: str | Path) -> "RouterConfig":
        path = Path(path)
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        cfg = raw.get("ws_router", {}) if isinstance(raw, dict) else {}

        return cls(**{k: v for k, v in cfg.items() if k in cls.__dataclass_fields__})
