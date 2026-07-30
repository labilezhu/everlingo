"""WS-Master 配置加载测试：env 展开（expand_env_vars + fail-loud）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from everlingo.ws_master.config import MasterConfig


def test_public_base_url_default_empty():
    cfg = MasterConfig()
    assert cfg.public_base_url == ""


def test_public_base_url_loaded_from_yaml(tmp_path: Path):
    yaml_path = tmp_path / "ws_master.yaml"
    yaml_path.write_text(
        "master:\n"
        "  public_base_url: https://app.everlingo.com\n",
        encoding="utf-8",
    )
    cfg = MasterConfig.load(yaml_path)
    assert cfg.public_base_url == "https://app.everlingo.com"


def test_public_base_url_env_expansion(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EVERLINGO_PUBLIC_BASE_URL", "https://from-env.everlingo.com")
    yaml_path = tmp_path / "ws_master.yaml"
    yaml_path.write_text(
        "master:\n"
        "  public_base_url: ${EVERLINGO_PUBLIC_BASE_URL}\n",
        encoding="utf-8",
    )
    cfg = MasterConfig.load(yaml_path)
    assert cfg.public_base_url == "https://from-env.everlingo.com"


def test_public_base_url_invalid_scheme_raises(tmp_path: Path):
    yaml_path = tmp_path / "ws_master.yaml"
    yaml_path.write_text(
        "master:\n"
        "  public_base_url: home130-everlingo.mygraphql.com:6457\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must start with http:// or https://"):
        MasterConfig.load(yaml_path)


def test_public_base_url_env_unset_is_literal_then_fails_scheme(
    tmp_path: Path, monkeypatch,
):
    monkeypatch.delenv("EVERLINGO_PUBLIC_BASE_URL", raising=False)
    yaml_path = tmp_path / "ws_master.yaml"
    yaml_path.write_text(
        "master:\n"
        "  public_base_url: ${EVERLINGO_PUBLIC_BASE_URL}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must start with http:// or https://"):
        MasterConfig.load(yaml_path)


def test_image_env_expansion(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WORKSPLACE_IMAGE", "ghcr.io/labilezhu/everlingo:latest")
    yaml_path = tmp_path / "ws_master.yaml"
    yaml_path.write_text(
        "master:\n"
        "  image: ${WORKSPLACE_IMAGE}\n"
        "  public_base_url: http://localhost\n",
        encoding="utf-8",
    )
    cfg = MasterConfig.load(yaml_path)
    assert cfg.image == "ghcr.io/labilezhu/everlingo:latest"


def test_openai_base_url_embedded_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENAI_HOST", "openrouter.ai")
    yaml_path = tmp_path / "ws_master.yaml"
    yaml_path.write_text(
        "master:\n"
        "  openai_base_url: https://${OPENAI_HOST}/api/v1\n"
        "  public_base_url: http://localhost\n",
        encoding="utf-8",
    )
    cfg = MasterConfig.load(yaml_path)
    assert cfg.openai_base_url == "https://openrouter.ai/api/v1"
