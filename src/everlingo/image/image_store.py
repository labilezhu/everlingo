# ref: docs/ADR/20260812-image-chat.md §14「存储位置」— 图片存储
# Phase 1：本地文件系统实现。逻辑键 storage_key=session://{session_id}/{sha256}
# 映射到物理路径 {workspace}/sessions/{session_id}/images/{sha256}.{ext}。
# 未来换对象存储只需替换本模块，调用方（上传端点、Agent 工具）不变。
# Phase 2：save() 引入 Pillow 预处理（EXIF 方向校正 → strip metadata → 超 1920x1200
# 按比例缩放），saved_resource_sha256 为处理后的标识（ADR §14 / §32）。

from __future__ import annotations

import hashlib
import logging
import math
import re
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps
from PIL.PngImagePlugin import PngInfo

from everlingo.image.models import ImageAsset
from everlingo.workspace import current_workspace, lang_vault_dir

logger = logging.getLogger(__name__)

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

# Pillow 保存格式（对齐 _MIME_EXT）
_MIME_PIL_FORMAT: dict[str, str] = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}

# ADR §14 / §32：最大像素数（1920x1200），超出按比例缩放
MAX_PIXELS = 1920 * 1200


def sha256_of_bytes(data: bytes) -> str:
    """计算字节的 SHA256 hex（即 src_resource_sha256 / saved_resource_sha256）。"""
    return hashlib.sha256(data).hexdigest()


_PIL_FORMAT_MIME: dict[str, str] = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


def sniff_image_mime(data: bytes) -> str | None:
    """从原始字节嗅探 MIME（jpeg/png/webp）；不可解析或未知格式返回 None。

    ref: docs/ADR/20260818-image-chat-wechat.md — 决策 4
    Wechat 下载字节不带 MIME/扩展名，靠 Pillow 读 format 映射。
    """
    try:
        with Image.open(BytesIO(data)) as img:
            fmt = img.format
    except Exception:
        return None
    return _PIL_FORMAT_MIME.get(fmt or "")


def preprocess_image(data: bytes, mime_type: str) -> tuple[bytes, int, int]:
    """ADP：EXIF 方向校正 → strip metadata → 超 1920x1200 按比例缩放。

    返回 (处理后字节, width, height)。图片不可解析时抛 ValueError
    （调用方映射为 400 IMAGE_INVALID）。
    """
    try:
        img = ImageOps.exif_transpose(Image.open(BytesIO(data)))
    except Exception as exc:
        raise ValueError("invalid image data") from exc

    if mime_type == "image/jpeg":
        img = img.convert("RGB")
    # copy 清空 info 以 strip 元数据（exif/text chunks），避免方向/隐私信息外泄
    img = img.copy()
    img.info.clear()

    width, height = img.size
    if width * height > MAX_PIXELS:
        scale = math.sqrt(MAX_PIXELS / (width * height))
        new_width = max(1, int(width * scale))
        new_height = max(1, int(height * scale))
        img = img.resize((new_width, new_height), Image.LANCZOS)
        width, height = new_width, new_height

    out = BytesIO()
    img.save(out, format=_MIME_PIL_FORMAT[mime_type])
    return out.getvalue(), width, height


# JPEG EXIF UserComment 标签（Pillow Exif tag id）
_EXIF_USER_COMMENT = 0x9286


def _is_valid_lang(lang: str) -> bool:
    """lang 名合法性校验（对齐 create_vault 的校验：防路径注入 / 逃逸）。"""
    return bool(
        isinstance(lang, str)
        and lang
        and "/" not in lang
        and "\\" not in lang
        and lang not in (".", "..")
        and "\x00" not in lang
    )


def _embed_self_metadata(processed: bytes, mime_type: str, src_sha: str) -> bytes:
    """best-effort：向处理后字节追加自有溯源元数据。

    - JPEG：写 EXIF UserComment="src_resource_sha256=<src_sha>"（tag 0x9286）。
    - PNG：写 tEXt 键 src_resource_sha256=<src_sha>。
    - 其余格式 / 任何异常：原样返回 processed（不阻断保存，失败静默）。
    仅写入自有元数据，不影响 preprocess 的隐私 strip。
    """
    try:
        img = Image.open(BytesIO(processed))
        out = BytesIO()
        if mime_type == "image/jpeg":
            exif = Image.Exif()
            exif[_EXIF_USER_COMMENT] = f"src_resource_sha256={src_sha}"
            img.save(out, format="JPEG", exif=exif, quality=95)
        elif mime_type == "image/png":
            pnginfo = PngInfo()
            pnginfo.add_text("src_resource_sha256", src_sha)
            img.save(out, format="PNG", pnginfo=pnginfo)
        else:
            return processed
        return out.getvalue()
    except Exception:
        logger.warning("embed self metadata failed for mime=%s, src=%s", mime_type, src_sha)
        return processed


# ref: docs/ADR/20260817-save-image-from-chat-to-note.md — 决策 1
# 用于 vault 图片文件名 {slug}-{src_sha[:8]}.{ext} 的 slug 归一化。
_SLUG_MAX_LEN = 40


def slugify(text: str) -> str:
    """把自由文本归一化为英文 slug（小写、非字母数字转 '-'、限长）。

    规则：小写 → 非 [a-z0-9] 连续块转 '-' → 折叠连续 '-' → 去首尾 '-' →
    限长 40 字符（避免截断到 '-' 结尾）→ 空串回退为 "image"。
    """
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    slug = slug[:_SLUG_MAX_LEN].rstrip("-")
    return slug or "image"


def save_vault_image(
    lang: str,
    vault_rel_path: str,
    data: bytes,
    mime_type: str,
    *,
    src_resource_sha256: str | None = None,
) -> ImageAsset:
    """把图片字节写入 lang vault 的相对路径，返回 ImageAsset（无状态、按路径幂等）。

    ref: docs/ADR/20260816-markdown-image.md — 决策 4 / 决策 5
    ref: docs/ADR/20260817-save-image-from-chat-to-note.md — 决策 2

    - 校验 MIME 允许列表。
    - src_resource_sha256 为可选 kwarg：
      - None（默认）：保留旧行为 —— vault_rel_path 末段 stem 作为 src_resource_sha256，
        由前端在 scale 前基于原始字节计算（ADR §8），服务端仅做 64 位 hex 格式校验，
        不再对收到的字节重算比对（前端可能已缩放，字节 sha ≠ 原始 sha）。
      - 显式传入：跳过 stem 64-hex 校验（stem 可为英文 slug，供 Chat Agent /
        Memory Writer 从 session 图片复制入 vault 使用）；对传入值本身做 64 位 hex
        校验，防止注入自有元数据（EXIF/tEXt）。
    - 复用 preprocess_image（EXIF 校正 → strip 元数据 → 超限缩放），随后 best-effort
      追加自有溯源元数据（JPEG EXIF / PNG tEXt）。
    - 写盘到 lang_vault_dir(lang).resolve() / vault_rel_path（父目录自动建）；
      文件已存在则跳过写盘（幂等）。
    - storage_key = memory://languages/{lang}/vault/{vault_rel_path}。
    - 与既有的 session 图片存储（ImageStore.save）并列，不改动其逻辑。
    """
    if mime_type not in ALLOWED_MIME:
        raise ValueError(f"unsupported mime type: {mime_type}")
    if not _is_valid_lang(lang):
        raise ValueError("invalid lang name")

    vault_root = lang_vault_dir(lang).resolve()
    if not vault_rel_path:
        raise ValueError("path escape")
    candidate = (vault_root / vault_rel_path).resolve()
    if not candidate.is_relative_to(vault_root):
        raise ValueError("path escape")

    if src_resource_sha256 is None:
        src_sha = candidate.stem
    else:
        src_sha = src_resource_sha256
    if not re.fullmatch(r"[0-9a-f]{64}", src_sha):
        raise ValueError("sha256 mismatch")

    processed, width, height = preprocess_image(data, mime_type)
    final = _embed_self_metadata(processed, mime_type, src_sha)
    saved_sha = sha256_of_bytes(final)

    candidate.parent.mkdir(parents=True, exist_ok=True)
    if not candidate.exists():
        candidate.write_bytes(final)

    storage_key = f"memory://languages/{lang}/vault/{vault_rel_path}"
    return ImageAsset(
        src_resource_sha256=src_sha,
        saved_resource_sha256=saved_sha,
        mime_type=mime_type,
        size=len(final),
        width=width,
        height=height,
        storage_key=storage_key,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


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

        # Phase 2：Pillow 预处理（EXIF 校正 → strip 元数据 → 超限缩放）。
        # saved_resource_sha256 用处理后的字节重算；cache key 沿用原始 src_resource_sha256
        #（ADR §21），使同一原图（无论保存形态）共享同一份分析。
        processed, width, height = preprocess_image(data, mime_type)
        saved_sha = sha256_of_bytes(processed)
        storage_key = f"session://{session_id}/{saved_sha}"

        directory = self._session_dir(session_id)
        directory.mkdir(parents=True, exist_ok=True)
        ext = _MIME_EXT[mime_type]
        file_path = directory / f"{saved_sha}.{ext}"
        if not file_path.exists():
            file_path.write_bytes(processed)

        asset = ImageAsset(
            src_resource_sha256=src_resource_sha256,
            saved_resource_sha256=saved_sha,
            mime_type=mime_type,
            size=len(processed),
            width=width,
            height=height,
            storage_key=storage_key,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._registry[src_resource_sha256] = asset
        return asset

    def get(self, src_resource_sha256: str) -> ImageAsset | None:
        return self._registry.get(src_resource_sha256)

    def read_bytes(self, src_resource_sha256: str) -> bytes | None:
        """按 src_resource_sha256 读回已存储（处理后的）图片字节；未注册返回 None。

        storage_key=session://{session_id}/{saved_sha} → 物理路径
        {workspace}/sessions/{session_id}/images/{saved_sha}.{ext}。
        ref: ADR §19 — Vision Service 从 ImageStore 取字节做 base64 data URI。
        """
        asset = self._registry.get(src_resource_sha256)
        if asset is None:
            return None
        # storage_key=session://{session_id}/{saved_sha}
        segments = asset.storage_key.split("/")
        if len(segments) < 4 or segments[0] != "session:" or segments[1] != "":
            return None
        session_id, saved_sha = segments[2], segments[3]
        ext = _MIME_EXT.get(asset.mime_type, "")
        file_path = self._session_dir(session_id) / f"{saved_sha}.{ext}"
        if not file_path.exists():
            return None
        return file_path.read_bytes()


# 进程级单例，供 web_acceptor 等共享。
image_store = ImageStore()
