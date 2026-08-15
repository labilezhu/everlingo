"""
analyze_image 工具单元测试：make_vision_tool

ref: docs/ADR/20260812-image-chat.md §12 / §22 / §29
验证工具返回 ImageAnalysis JSON、Vision 失败时返回自然语言降级而非抛异常。
"""
import json

import pytest

from everlingo.image.models import ImageAnalysis, ImageInput
from everlingo.image.vision_service import VisionServiceError
from everlingo.tools.vision_tool import make_vision_tool


class FakeVisionService:
    def __init__(self, analysis=None, error=None):
        self._analysis = analysis
        self._error = error
        self.called_with = None

    async def analyze(self, image: ImageInput, *, purpose=None):
        self.called_with = image
        if self._error is not None:
            raise self._error
        return self._analysis or ImageAnalysis(src_resource_sha256=image.src_resource_sha256)


def _make_tool(service):
    return make_vision_tool(service)


class TestVisionTool:
    @pytest.mark.asyncio
    async def test_returns_analysis_json(self):
        svc = FakeVisionService()
        tool = _make_tool(svc)
        out = await tool.ainvoke({"src_resource_sha256": "sha-123"})

        assert isinstance(out, str)
        data = json.loads(out)
        assert data["src_resource_sha256"] == "sha-123"
        assert svc.called_with.src_resource_sha256 == "sha-123"

    @pytest.mark.asyncio
    async def test_vision_error_returns_friendly_text(self):
        svc = FakeVisionService(error=VisionServiceError("model down"))
        tool = _make_tool(svc)
        out = await tool.ainvoke({"src_resource_sha256": "sha-456"})

        assert isinstance(out, str)
        assert "无法识别" in out
        assert "VISION_ANALYSIS_FAILED" in out

    @pytest.mark.asyncio
    async def test_respects_provided_analysis(self):
        analysis = ImageAnalysis(
            src_resource_sha256="sha-x",
            content_type="english_exercise",
            text="What is 2+2?",
        )
        svc = FakeVisionService(analysis=analysis)
        tool = _make_tool(svc)
        out = await tool.ainvoke({"src_resource_sha256": "sha-x"})
        data = json.loads(out)
        assert data["content_type"] == "english_exercise"
        assert data["text"] == "What is 2+2?"