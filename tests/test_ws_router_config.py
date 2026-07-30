"""WS-Router 配置加载测试：env 展开（expand_env_vars）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from everlingo.ws_router.config import RouterConfig


def _write_config(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "ws_router.yaml"
    p.write_text(content, encoding="utf-8")
    return p


def test_master_secret_env_expansion(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MASTER_SECRET", "test-secret-abc123")
    yaml_path = _write_config(
        tmp_path,
        "ws_router:\n"
        "  master_secret: ${MASTER_SECRET}\n"
        "  jwt_secret: dummy\n"
        "  public_base_url: http://localhost\n",
    )
    cfg = RouterConfig.load(yaml_path)
    assert cfg.master_secret == "test-secret-abc123"


def test_public_base_url_embedded_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EVERLINGO_HOST", "app.everlingo.com")
    yaml_path = _write_config(
        tmp_path,
        "ws_router:\n"
        "  public_base_url: https://${EVERLINGO_HOST}\n"
        "  jwt_secret: dummy\n",
    )
    cfg = RouterConfig.load(yaml_path)
    assert cfg.public_base_url == "https://app.everlingo.com"


def test_literal_value_no_expansion(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("NONEXISTENT_VAR", raising=False)
    yaml_path = _write_config(
        tmp_path,
        "ws_router:\n"
        "  master_secret: ${NONEXISTENT_VAR}\n"
        "  jwt_secret: dummy\n"
        "  public_base_url: http://localhost\n",
    )
    cfg = RouterConfig.load(yaml_path)
    assert cfg.master_secret == "${NONEXISTENT_VAR}"
