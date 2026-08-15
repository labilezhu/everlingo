"""
Vision Service 单元测试：OpenRouterVisionService

ref: docs/ADR/20260812-image-chat.md §19 / §21 / §22 / §23 / §29
验证：目的 prompt 分流、JSON 解析、缓存命中、in_flight 合并、错误映射。
不使用真实 LLM（fake 对象注入）。
"""
import asyncio
import json
from io import BytesIO

import pytest
from langchain_core.messages import AIMessage

from everlingo.image.image_store import ImageStore, sha256_of_bytes
from everlingo.image.models import ImageAnalysis, ImageInput, VisionPurpose
from everlingo.image.vision_service import (
    OpenRouterVisionService,
    VisionModelUnavailableError,
    VisionOutputInvalidError,
    VisionServiceError,
)
from everlingo.workspace import init_workspace_dir


@pytest.fixture
def store(tmp_path):
    init_workspace_dir(tmp_path)
    yield ImageStore()
    init_workspace_dir(None)


def _png_bytes(size=(64, 48)) -> bytes:
    from PIL import Image

    img = Image.new("RGB", size, (10, 200, 10))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class FakeLLM:
    """mock ChatOpenAI：记录调用次数与系统 prompt，返回预置 JSON。"""

    model_name = "fake-vision-model"

    def __init__(self):
        self.calls = 0
        self.system_prompts: list[str] = []

    async def ainvoke(self, messages):
        self.calls += 1
        text_only = True
        for m in messages:
            if getattr(m, "type", "") == "system":
                self.system_prompts.append(str(m.content))
            # 图片消息应含 image_url content parts
            if m.type == "human" and isinstance(m.content, list):
                if any(c.get("type") == "image_url" for c in m.content):
                    text_only = False
        self.last_image_missing = text_only
        return AIMessage(
            content=json.dumps({
                "content_type": "english_exercise",
                "language": ["en"],
                "text": "I have lived here _____ 2019.\nA. for\nB. since",
                "structured_content": {"type": "multiple_choice", "questions": []},
                "knowledge_points": [],
            })
        )


class FailingLLM:
    model_name = "fake-vision-model"

    async def ainvoke(self, messages):
        raise RuntimeError("boom")


class _FailingFactoryLLM:
    """llm_factory 抛错 → VISION_MODEL_UNAVAILABLE。"""

    def __init__(self):
        raise RuntimeError("no api key")


def _service(store, llm):
    return OpenRouterVisionService(store=store, llm_factory=lambda: llm)


def _saved_src(store, raw) -> str:
    src = sha256_of_bytes(raw)
    store.save("sess-1", src, raw, "image/png")
    return src


class TestVisionServiceAnalyze:
    def test_returns_analysis(self, store):
        llm = FakeLLM()
        svc = _service(store, llm)
        src = _saved_src(store, _png_bytes())

        analysis = asyncio.run(svc.analyze(ImageInput(src_resource_sha256=src)))

        assert isinstance(analysis, ImageAnalysis)
        assert analysis.src_resource_sha256 == src
        assert analysis.content_type == "english_exercise"
        assert analysis.text.startswith("I have lived here")
        assert analysis.model == {"provider": "openrouter", "model": "fake-vision-model"}
        assert llm.calls == 1

    def test_purpose_prompt_specialization(self, store):
        llm = FakeLLM()
        svc = _service(store, llm)
        src = _saved_src(store, _png_bytes())

        asyncio.run(svc.analyze(ImageInput(src_resource_sha256=src), purpose=VisionPurpose.EXERCISE))

        assert llm.system_prompts, "应注入 system prompt"
        assert "习题" in llm.system_prompts[0]

    def test_in_flight_concurrent_calls_single_model_invoke(self, store):
        """并发对同一 sha256 → 至多一次 Vision Model 调用（§23）。"""
        llm = FakeLLM()
        svc = _service(store, llm)
        src = _saved_src(store, _png_bytes())

        async def run():
            img = ImageInput(src_resource_sha256=src)
            return await asyncio.gather(
                svc.analyze(img), svc.analyze(img), svc.analyze(img)
            )

        results = asyncio.run(run())
        assert len(results) == 3
        assert llm.calls == 1

    def test_cache_hit_avoids_second_invoke(self, store):
        llm = FakeLLM()
        svc = _service(store, llm)
        src = _saved_src(store, _png_bytes())

        async def run():
            img = ImageInput(src_resource_sha256=src)
            first = await svc.analyze(img)
            second = await svc.analyze(img)
            return first, second

        first, second = asyncio.run(run())
        assert first == second
        assert llm.calls == 1


class TestVisionServiceErrors:
    def test_missing_image_raises(self, store):
        svc = _service(store, FakeLLM())
        with pytest.raises(VisionServiceError, match="image not found"):
            asyncio.run(svc.analyze(ImageInput(src_resource_sha256="unknown")))

    def test_invalid_json_output_raises(self, store):
        class BadLLM:
            model_name = "fake-vision-model"

            async def ainvoke(self, messages):
                return AIMessage(content="not json at all")

        svc = _service(store, BadLLM())
        src = _saved_src(store, _png_bytes())
        with pytest.raises(VisionOutputInvalidError):
            asyncio.run(svc.analyze(ImageInput(src_resource_sha256=src)))

    def test_model_call_failure_maps(self, store):
        svc = _service(store, FailingLLM())
        src = _saved_src(store, _png_bytes())
        with pytest.raises(VisionServiceError):
            asyncio.run(svc.analyze(ImageInput(src_resource_sha256=src)))

    def test_llm_construction_failure_maps_unavailable(self, store):
        svc = OpenRouterVisionService(store=store, llm_factory=_FailingFactoryLLM)
        src = _saved_src(store, _png_bytes())
        with pytest.raises(VisionModelUnavailableError):
            asyncio.run(svc.analyze(ImageInput(src_resource_sha256=src)))