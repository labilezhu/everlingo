# ref: docs/ADR/20260812-image-chat.md §14「存储位置」— 图片存储
# Phase 1：本地文件系统实现。逻辑键 storage_key=session://{session_id}/{sha256}
# 映射到物理路径 {workspace}/sessions/{session_id}/images/{sha256}.{ext}。
# 未来换对象存储只需替换本模块，调用方（上传端点、Agent 工具）不变。

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from everlingo.image.models import ImageAsset
from everlingo.workspace import current_workspace

# 允许的 MIME（对齐 ADR §32 MVP 资源限制）
ALLOWED_MIME: set[str] = {
    "image/jpeg",
    "image/png",
    "image/webp",
}

_MIME_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def sha256_of_bytes(data: bytes) -> str:
    """计算字节的 SHA256 hex（即 src_resource_sha256 / saved_resource_sha256）。"""
    return hashlib.sha256(data).hexdigest()


class ImageStore:
    """本地文件系统的图片存储。

    - 物理落盘：{workspace}/sessions/{session_id}/images/{sha256}.{ext}
    - 内存注册表：src_resource_sha256 -> ImageAsset，用于幂等/去重（单进程内）。
    """

    def __init__(self) -> None:
        self._registry: dict[str, ImageAsset] = {}

    def _session_dir(self, session_id: str) -> Path:
        return current_workspace() / "sessions" / session_id / "images"

    def save(
        self,
        session_id: str,
        src_resource_sha256: str,
        data: bytes,
        mime_type: str,
    ) -> ImageAsset:
        """存储图片字节并返回 ImageAsset。

        - 校验 MIME 是否允许。
        - 重新计算 sha256 与入参 src_resource_sha256 比对，不一致视为客户端计算错误。
        - Phase 1 不做缩放/校正：saved_resource_sha256 == src_resource_sha256。
        - 同 sha256 重复上传：返回已注册的 ImageAsset（幂等），不重复写盘/不改变元数据。
        """
        if mime_type not in ALLOWED_MIME:
            raise ValueError(f"unsupported mime type: {mime_type}")

        actual_sha = sha256_of_bytes(data)
        if actual_sha != src_resource_sha256:
            raise ValueError("sha256 mismatch")

        existing = self._registry.get(src_resource_sha256)
        if existing is not None:
            return existing

        ext = _MIME_EXT[mime_type]
        # Phase 1：saved == src（无处理）
        saved_sha = src_resource_sha256
        storage_key = f"session://{session_id}/{saved_sha}"

        directory = self._session_dir(session_id)
        directory.mkdir(parents=True, exist_ok=True)
        file_path = directory / f"{saved_sha}.{ext}"
        if not file_path.exists():
            file_path.write_bytes(data)

        asset = ImageAsset(
            src_resource_sha256=src_resource_sha256,
            saved_resource_sha256=saved_sha,
            mime_type=mime_type,
            size=len(data),
            width=None,
            height=None,
            storage_key=storage_key,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._registry[src_resource_sha256] = asset
        return asset

    def get(self, src_resource_sha256: str) -> ImageAsset | None:
        return self._registry.get(src_resource_sha256)


# 进程级单例，供 web_acceptor 等共享。
image_store = ImageStore()
