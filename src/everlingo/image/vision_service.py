# ref: docs/ADR/20260812-image-chat.md §19 / §20 / §21 / §22 / §23 / §29
# Vision Service：感知层（"图片里有什么"），不产出业务答案（§10）。
# - OpenRouterVisionService：读 ImageStore 字节 → base64 data URI → ChatOpenAI vision。
# - 缓存 + 并发防护：persistent_cache(LRU/TTL) + in_flight(Future 合并)，单进程 MVP（§23）。

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Callable, Protocol

from langchain_core.messages import HumanMessage, SystemMessage

from everlingo.image.image_store import ImageStore, image_store as _default_image_store
from everlingo.image.models import ImageAnalysis, ImageInput, VisionPurpose
from everlingo.llm import create_vision_llm

logger = logging.getLogger(__name__)

# ADR §21：prompt 版本参与 cache key，修改 Vision prompt 时 +1。
PROMPT_VERSION = 1
# ADR §32：analysis retention — LRU + TTL（7 天），与 session 解耦。
CACHE_TTL_SECONDS = 7 * 24 * 3600
MAX_CACHE_SIZE = 256

# Provider 名称（唯一 provider，未来扩展 Gemini/OpenAI/Anthropic）。
VISION_PROVIDER = "openrouter"

# ADR §29 — Vision Service 错误码
class VisionServiceError(Exception):
    """Vision 分析失败的基类（工具层据此降级为自然语言提示）。"""

    code = "VISION_ANALYSIS_FAILED"


class VisionModelUnavailableError(VisionServiceError):
    code = "VISION_MODEL_UNAVAILABLE"


class VisionOutputInvalidError(VisionServiceError):
    code = "VISION_OUTPUT_INVALID"


# ---- Purpose 专用 system prompt（ADR §20）----------------------------------


def _build_system_prompt(purpose: VisionPurpose | None) -> str:
    base = """你是 EverLingo 的图片理解（Vision）模块，只负责"看出图片里有什么"，不负责答题、
讲解或给出学习建议——那是另一个专业 Agent 的任务。
请识别图片内容，并仅输出一个 JSON 对象（不要 markdown 代码块、不要任何额外文字），字段：
- content_type: 字符串。可选 "english_exercise"（英语习题）、"exercise"（其他习题）、
  "document"（文档/文章）、"ocr"（纯文字）、"general"（其他）。
- language: 图片中文字的语言代码列表，如 ["en"]、["zh"]、["ja"]。
- text: 识别出的图片文字，尽量贴近原图排版，保留换行。
- structured_content: 面向业务的结构化对象。习题图片给
  {"type":"multiple_choice","questions":[{"question":"...","options":[{"label":"A","text":"..."},"..."]}]}
  （选择题）；无法结构化时给 {"type":"general"}。
- knowledge_points: 相关知识点标签数组，暂无则为 []。
禁止输出 answer/explanation/解析/翻译/点评。
"""
    hints = {
        VisionPurpose.OCR: "这是一个纯 OCR 任务：text 必须尽可能完整逐字还原图片文字；"
                           "structured_content 给 {\"type\":\"ocr\"} 即可，knowledge_points 为 []。",
        VisionPurpose.EXERCISE: "这是习题图片：text 原样给出题目文字，structured_content 侧重"
                                "识别题型并把题目/选项结构化；不要解答。",
        VisionPurpose.DOCUMENT: "这是文档/文章图片：text 按段落还原文字；structured_content 给"
                                " {\"type\":\"document\",\"sections\":[...]} 按节归纳。",
        VisionPurpose.LEARNING_CONTENT: "这是学习材料图片：除 text 外，knowledge_points 尽量给出"
                                        "与当前学习目标相关的知识点标签；structured_content 侧重"
                                        "语义结构。",
        VisionPurpose.GENERAL: "",
        None: "",
    }
    hint = hints.get(purpose, "")
    return (base + "\n" + hint).strip() if hint else base.strip()


def _extract_json(text: str) -> dict | None:
    """从模型输出中提取首个 JSON 对象（容忍 markdown 代码块）。"""
    candidates = [text.strip()]
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        candidates.insert(0, fenced.group(1))
    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue
    return None


# ---- Service ----------------------------------------------------------------

class VisionService(Protocol):
    async def analyze(
        self,
        image: ImageInput,
        *,
        purpose: VisionPurpose | None = None,
    ) -> ImageAnalysis:
        ...


class OpenRouterVisionService:
    """基于 OpenRouter ChatOpenAI 的 Vision Service 实现（ADR §19）。"""

    def __init__(
        self,
        store: ImageStore | None = None,
        llm_factory: Callable = create_vision_llm,
    ) -> None:
        self._store = store or _default_image_store
        self._llm_factory = llm_factory
        self._llm: object | None = None
        self._model: str = ""
        self._persistent_cache: "OrderedDict[str, tuple[float, ImageAnalysis]]" = OrderedDict()
        self._in_flight: dict[str, "asyncio.Future[ImageAnalysis]"] = {}

    def _get_llm(self):
        if self._llm is None:
            self._llm = self._llm_factory()
            self._model = str(getattr(self._llm, "model_name", "") or self._llm.model_name)
        return self._llm

    # ---- cache（ADR §21 / §23） -----------------------------------------

    def _cache_key(self, src_sha: str, model: str, purpose: VisionPurpose | None) -> str:
        # key = src_resource_sha256 + model + prompt_version（§21），另加 purpose
        # 区分不同分析目的（§20 影响 prompt，故并入 key 避免串结果）。
        return f"{src_sha}|{model}|v{PROMPT_VERSION}|{purpose.value if purpose else 'general'}"

    def _cache_get(self, key: str) -> ImageAnalysis | None:
        entry = self._persistent_cache.get(key)
        if entry is None:
            return None
        ts, analysis = entry
        if datetime.now(timezone.utc).timestamp() - ts > CACHE_TTL_SECONDS:
            self._persistent_cache.pop(key, None)
            return None
        self._persistent_cache.move_to_end(key)
        return analysis

    def _cache_put(self, key: str, analysis: ImageAnalysis) -> None:
        self._persistent_cache[key] = (datetime.now(timezone.utc).timestamp(), analysis)
        self._persistent_cache.move_to_end(key)
        while len(self._persistent_cache) > MAX_CACHE_SIZE:
            self._persistent_cache.popitem(last=False)

    # ---- analyze --------------------------------------------------------

    async def analyze(
        self,
        image: ImageInput,
        *,
        purpose: VisionPurpose | None = None,
    ) -> ImageAnalysis:
        """cache-first + in_flight 合并（ADR §22 Tool Fetch / §23 并发防护）。

        同一 key 的 Vision Model 调用至多一次：命中持久缓存直接返回；
        已 in_flight 则 await 同一 Future（Eager Warm 与 Agent 工具并发安全）。
        """
        try:
            model = self._model or (self._get_llm().model_name or "")
        except Exception as exc:
            logger.warning(
                "vision llm construction failed (analyze): %s", type(exc).__name__,
                exc_info=True,
            )
            raise VisionModelUnavailableError(str(exc)) from exc

        key = self._cache_key(image.src_resource_sha256, model, purpose)

        cached = self._cache_get(key)
        if cached is not None:
            logger.debug("vision cache hit: %s", key)
            return cached

        in_flight = self._in_flight.get(key)
        if in_flight is not None:
            logger.debug("vision in_flight join: %s", key)
            return await asyncio.shield(in_flight)

        fut = asyncio.ensure_future(self._do_analyze(image, purpose, key))
        self._in_flight[key] = fut
        try:
            return await fut
        finally:
            self._in_flight.pop(key, None)

    async def _do_analyze(
        self,
        image: ImageInput,
        purpose: VisionPurpose | None,
        key: str,
    ) -> ImageAnalysis:
        asset = self._store.get(image.src_resource_sha256)
        if asset is None:
            raise VisionServiceError(f"image not found: {image.src_resource_sha256}")
        data = self._store.read_bytes(image.src_resource_sha256)
        if data is None:
            raise VisionServiceError(f"image bytes missing: {image.src_resource_sha256}")

        data_uri = (
            f"data:{asset.mime_type};base64,"
            f"{base64.b64encode(data).decode('ascii')}"
        )
        messages = [
            SystemMessage(content=_build_system_prompt(purpose)),
            HumanMessage(
                content=[
                    {"type": "text", "text": "请分析这张图片。"},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ]
            ),
        ]

        try:
            llm = self._get_llm()
        except Exception as exc:
            logger.warning(
                "vision llm construction failed: %s key=%s",
                type(exc).__name__, key,
                exc_info=True,
            )
            raise VisionModelUnavailableError(str(exc)) from exc

        try:
            response = await llm.ainvoke(messages)
        except Exception as exc:
            logger.warning(
                "vision model call failed: %s key=%s", type(exc).__name__, key,
                exc_info=True,
            )
            raise VisionServiceError(str(exc)) from exc

        payload = _extract_json(getattr(response, "content", "") or "")
        if payload is None:
            raise VisionOutputInvalidError("vision output is not valid JSON")
        try:
            analysis = ImageAnalysis(
                src_resource_sha256=image.src_resource_sha256,
                model={
                    "provider": VISION_PROVIDER,
                    "model": self._model,
                },
                content_type=str(payload.get("content_type", "general")),
                language=list(payload.get("language") or []),
                text=str(payload.get("text") or ""),
                structured_content=dict(payload.get("structured_content") or {}),
                knowledge_points=list(payload.get("knowledge_points") or []),
            )
        except Exception as exc:
            raise VisionOutputInvalidError(f"invalid vision output: {exc}") from exc

        self._cache_put(key, analysis)
        return analysis


# 进程级单例，供 web_acceptor（Eager Warm）与 Agent 工具共享。
# 惰性创建：llm 首次 analyze 时才构造，避免 import 期依赖 LLM 配置。
vision_service = OpenRouterVisionService()