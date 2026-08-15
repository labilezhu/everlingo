# ref: docs/ADR/20260812-image-chat.md §7 / §8 / §9 / §19 / §20 — 图片数据模型
# Phase 1：仅后端上传与存储所需字段；width/height 在引入 Pillow（Phase 2 缩放/校正）后填充。
# Phase 2：新增 VisionPurpose / ImageInput / ImageAnalysis（Vision Service 感知结果）。

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class VisionPurpose(str, Enum):
    """Vision 分析目的，用于让模型 prompt 更专化（ADR §20）。

    注：使用 str Enum，序列化为原始字符串（如 "exercise"）。
    """

    OCR = "ocr"
    EXERCISE = "exercise"
    DOCUMENT = "document"
    LEARNING_CONTENT = "learning_content"
    GENERAL = "general"


class ImageInput(BaseModel):
    """Vision 分析的输入引用。

    ref: ADR §19 — analyze(image: ImageInput)
    Phase 2（无多资源场景）仅承载 src_resource_sha256；VisionService 据此从
    ImageStore 读回字节。未来扩展到多图/混合资源时在此扩展字段。
    """

    src_resource_sha256: str


class ImageAnalysis(BaseModel):
    """Vision Service 的核心输出（感知层结果，不含业务答案）。

    ref: ADR §9 — ImageAnalysis
    ref: ADR §10 — Vision 只回答「图片里有什么」，不输出 answer/explanation。

    - text: 尽量接近图片中的原始文字（OCR 层）。
    - structured_content: 面向业务的语义结构（理解层）；形态随 content_type
      变化（选择题/文档/单词卡…），Phase 2 用宽松 dict 容纳，不强 schema。
    - src_resource_sha256 + model + prompt_version 共同构成缓存 key（§21）。
    """

    src_resource_sha256: str
    model: dict[str, str] = Field(default_factory=dict)  # {"provider": ..., "model": ...}
    content_type: str = "general"
    language: list[str] = Field(default_factory=list)
    text: str = ""
    structured_content: dict[str, Any] = Field(default_factory=dict)
    knowledge_points: list[str] = Field(default_factory=list)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ImageAsset(BaseModel):
    """上传成功后的图片文件元数据。

    ref: ADR §7 — ImageAsset
    src_resource_sha256 / saved_resource_sha256 分离：前者是用户端原图标识（幂等上传、
    cache key），后者是服务端处理后（缩放/校正）的存储标识。Phase 1 两者相等，
    Phase 2 引入 Pillow 缩放/EXIF 校正后 saved 为处理后的标识。
    """

    src_resource_sha256: str
    saved_resource_sha256: str
    mime_type: str
    size: int
    width: int | None = None
    height: int | None = None
    storage_key: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class MessageAttachment(BaseModel):
    """消息对图片（未来扩展 file/audio/video）的引用。

    ref: ADR §8 — MessageAttachment
    只携带 src_resource_sha256，不内联图片字节或分析结果。
    """

    src_resource_sha256: str
    type: Literal["image"] = "image"
