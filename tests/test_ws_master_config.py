"""WS-Master 配置加载测试：public_base_url 字段与 env 展开。"""

from __future__ import annotations

from pathlib import Path

from everlingo.ws_master.config import MasterConfig


def test_public_base_url_default_empty():
    """未配置时 public_base_url 默认空串。"""
    cfg = MasterConfig()
    assert cfg.public_base_url == ""


def test_public_base_url_loaded_from_yaml(tmp_path: Path):
    """ws_master.yaml 的 public_base_url 直接加载。"""
    yaml_path = tmp_path / "ws_master.yaml"
    yaml_path.write_text(
        "master:\n"
        "  public_base_url: https://app.everlingo.com\n",
        encoding="utf-8",
    )
    cfg = MasterConfig.load(yaml_path)
    assert cfg.public_base_url == "https://app.everlingo.com"


def test_public_base_url_env_expansion(tmp_path: Path, monkeypatch):
    """public_base_url 支持 ${VAR} env 展开（与 openai_* 同形）。"""
    monkeypatch.setenv("EVERLINGO_PUBLIC_BASE_URL", "https://from-env.everlingo.com")
    yaml_path = tmp_path / "ws_master.yaml"
    yaml_path.write_text(
        "master:\n"
        "  public_base_url: ${EVERLINGO_PUBLIC_BASE_URL}\n",
        encoding="utf-8",
    )
    cfg = MasterConfig.load(yaml_path)
    assert cfg.public_base_url == "https://from-env.everlingo.com"


def test_public_base_url_env_unset_falls_back_to_empty(tmp_path: Path, monkeypatch):
    """${VAR} 但 env 未设 → 空串（不影响 setting.py 的 listener 回退）。"""
    monkeypatch.delenv("EVERLINGO_PUBLIC_BASE_URL", raising=False)
    yaml_path = tmp_path / "ws_master.yaml"
    yaml_path.write_text(
        "master:\n"
        "  public_base_url: ${EVERLINGO_PUBLIC_BASE_URL}\n",
        encoding="utf-8",
    )
    cfg = MasterConfig.load(yaml_path)
    assert cfg.public_base_url == ""
