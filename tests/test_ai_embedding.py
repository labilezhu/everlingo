# ref: docs/impl-spec/search/memory-vault-search-spec.md — Embedding 封装
# AIEmbedding 单元测试（mock 配置 / 不联网）+ 集成测试（真实调 OpenRouter）。

from __future__ import annotations

import os
from typing import Any

import pytest

from everlingo.config import get_llm_config
from everlingo.mem.vault.search.embedding.ai_embedding import AIEmbedding
from everlingo.models import EverLingoSetting, SysSetting


# ── helpers ──────────────────────────────────────────────────────────


def _make_setting(**overrides: Any) -> EverLingoSetting:
    """构造仅含 sys_setting 的 EverLingoSetting，便于 monkeypatch。"""
    return EverLingoSetting(sys_setting=SysSetting(**overrides))


def _patch_config(monkeypatch: pytest.MonkeyPatch, **env: str) -> None:
    """清空相关 env，再注入测试值；monkeypatch 掉 load_setting 返回空 sys_setting。"""
    for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_EMBEDDING_MODEL"):
        monkeypatch.delenv(key, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    # 隔离工作区 setting：让 sys_setting 取自 env，不被 workspace yaml 干扰
    monkeypatch.setattr(
        "everlingo.config.load_setting",
        lambda: _make_setting(),
    )


# ── unit tests ───────────────────────────────────────────────────────


def test_create_raises_when_embedding_model_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """OPENAI_EMBEDDING_MODEL 为空时 create() 抛 ValueError。"""
    _patch_config(
        monkeypatch,
        OPENAI_API_KEY="sk-test",
        OPENAI_BASE_URL="https://openrouter.ai/api/v1",
    )
    with pytest.raises(ValueError, match="OPENAI_EMBEDDING_MODEL 未设置"):
        AIEmbedding.create()


def test_create_uses_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """配置完整时 create() 返回带正确字段的 AIEmbedding。"""
    _patch_config(
        monkeypatch,
        OPENAI_API_KEY="sk-test",
        OPENAI_BASE_URL="https://openrouter.ai/api/v1",
        OPENAI_EMBEDDING_MODEL="openai/text-embedding-3-small",
    )
    emb = AIEmbedding.create()
    assert isinstance(emb, AIEmbedding)
    assert emb.model == "openai/text-embedding-3-small"
    assert emb.openai_api_base == "https://openrouter.ai/api/v1"
    assert emb.openai_api_key.get_secret_value() == "sk-test"
    # OpenRouter 兼容：必须关掉 tiktoken
    assert emb.tiktoken_enabled is False
    assert emb.check_embedding_ctx_length is False


def test_create_sys_setting_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """everlingo.yaml sys_setting.openai_embedding_model 优先级高于 env。"""
    _patch_config(
        monkeypatch,
        OPENAI_API_KEY="sk-test",
        OPENAI_BASE_URL="https://openrouter.ai/api/v1",
        OPENAI_EMBEDDING_MODEL="from-env",
    )
    monkeypatch.setattr(
        "everlingo.config.load_setting",
        lambda: _make_setting(
            openai_api_key="sk-yaml",
            openai_base_url="https://yaml.api/v1",
            openai_embedding_model="from-yaml",
        ),
    )
    emb = AIEmbedding.create()
    assert emb.model == "from-yaml"
    assert emb.openai_api_base == "https://yaml.api/v1"
    assert emb.openai_api_key.get_secret_value() == "sk-yaml"


def test_get_llm_config_includes_embedding_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_llm_config() 返回 embedding_model 键。"""
    _patch_config(
        monkeypatch,
        OPENAI_API_KEY="sk-test",
        OPENAI_EMBEDDING_MODEL="m-x",
    )
    cfg = get_llm_config()
    assert cfg["embedding_model"] == "m-x"


# ── integration tests (real OpenRouter call) ─────────────────────────


@pytest.mark.integration
def test_integration_embed_query_real() -> None:
    """真实调 OpenRouter embedding endpoint。需 .env 含 OPENAI_EMBEDDING_MODEL。"""
    if not os.getenv("OPENAI_EMBEDDING_MODEL"):
        pytest.skip("OPENAI_EMBEDDING_MODEL 未配置，跳过 integration 测试")
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY 未配置，跳过 integration 测试")
    emb = AIEmbedding.create()
    vec = emb.embed_query("hello world")
    assert isinstance(vec, list)
    assert len(vec) > 0
    assert all(isinstance(x, float) for x in vec)

 
@pytest.mark.integration
def test_integration_embed_documents_real() -> None:
    """embed_documents 真实调用：返回向量数量与输入一致，维度一致。"""
    if not os.getenv("OPENAI_EMBEDDING_MODEL"):
        pytest.skip("OPENAI_EMBEDDING_MODEL 未配置，跳过 integration 测试")
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY 未配置，跳过 integration 测试")
    emb = AIEmbedding.create()
    texts = ["apple", "banana"]
    vecs = emb.embed_documents(texts)
    assert len(vecs) == len(texts)
    dim = len(vecs[0])
    assert dim > 0
    assert all(len(v) == dim for v in vecs)
