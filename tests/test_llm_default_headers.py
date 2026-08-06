"""
单元测试：LLM 请求携带应用标识 headers (User-Agent / HTTP-Referer / X-Title)

验证：
- _build_llm 构造 ChatOpenAI 时传入 default_headers
- User-Agent 格式为 `EverLingo/<__version__>`，且与包版本一致
- HTTP-Referer 与 X-Title 正确
- 所有 LLM 工厂 (create_llm / create_extract_llm / create_mem_writer_llm)
  均携带 default_headers
"""
import pytest

import everlingo
from everlingo import llm as llm_mod


class _ChatOpenAIStub:
    """捕获 ChatOpenAI 构造参数的替身。"""

    instances: list[dict] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        _ChatOpenAIStub.instances.append(kwargs)


@pytest.fixture(autouse=True)
def _stub_llm(monkeypatch):
    monkeypatch.setattr(llm_mod, "ChatOpenAI", _ChatOpenAIStub)
    monkeypatch.setattr(
        llm_mod,
        "get_llm_config",
        lambda: {"api_key": "k", "base_url": "https://openrouter.ai/api/v1", "model": "m"},
    )
    monkeypatch.setattr(llm_mod, "setup_tracing", lambda: None)
    monkeypatch.setattr(llm_mod, "LLMLoggingHandler", lambda: object())
    _ChatOpenAIStub.instances.clear()
    yield
    _ChatOpenAIStub.instances.clear()


class TestDefaultHeaders:
    def test_build_llm_passes_default_headers(self):
        llm_mod._build_llm()
        kwargs = _ChatOpenAIStub.instances[0]
        headers = kwargs["default_headers"]
        assert headers["HTTP-Referer"] == "https://github.com/labilezhu/everlingo"
        assert headers["X-Title"] == "EverLingo"

    def test_user_agent_matches_package_version(self):
        llm_mod._build_llm()
        kwargs = _ChatOpenAIStub.instances[0]
        assert kwargs["default_headers"]["User-Agent"] == f"EverLingo/{everlingo.__version__}"
        assert everlingo.__version__ == "0.1.1-rc.4"

    def test_all_llm_factories_carry_headers(self):
        llm_mod.create_llm()
        llm_mod.create_extract_llm()
        llm_mod.create_mem_writer_llm()
        assert len(_ChatOpenAIStub.instances) == 3
        for kwargs in _ChatOpenAIStub.instances:
            assert "default_headers" in kwargs
            assert kwargs["default_headers"]["User-Agent"].startswith("EverLingo/")
