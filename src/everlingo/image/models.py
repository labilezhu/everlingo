# ref: docs/ADR/20260812-image-chat.md §7 / §8 — 图片数据模型
# Phase 1：仅后端上传与存储所需字段；width/height 在引入 Pillow（Phase 2 缩放/校正）后填充。

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class ImageAsset(BaseModel):
    """上传成功后的图片文件元数据。

    ref: ADR §7 — ImageAsset
    src_resource_sha256 / saved_resource_sha256 分离：前者是用户端原图标识（幂等上传、
    cache key），后者是服务端处理后（缩放/校正）的存储标识。Phase 1 不做处理，两者相等。
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
