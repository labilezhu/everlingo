# ref: docs/ADR/20260817-save-image-from-chat-to-note.md — 决策 3 / 决策 4
# copy_session_image_to_vault 工具：把聊天 session 中某张已上传图片复制到目标笔记
# markdown 的 .assets 目录，返回 markdown 相对引用路径。
# 与 make_vision_tool / make_memory_writer_action_tool 同模式：工厂返回
# StructuredTool，绑定特定 ImageStore 与目标语言（vault lang）。
# 注入点：
#   - Chat Agent（编辑流程）：_refresh_agent_if_needed，仅 channel.supported_image 时。
#   - Memory Writer（create 流程）：_write_kb_item_async，per-entry 追加。

from __future__ import annotations

import json
import logging
import posixpath
from typing import TYPE_CHECKING

from langchain_core.tools import StructuredTool, tool
from pydantic import BaseModel, Field

from . import log_tool_call

if TYPE_CHECKING:
    from ..image.image_store import ImageStore

logger = logging.getLogger(__name__)


class _CopySessionImageArgs(BaseModel):
    src_resource_sha256: str = Field(
        ...,
        description=(
            "图片标识：用户消息 envelope.chat.attachments[].src_resource_sha256"
            "或 analyze_image 工具结果中的 src_resource_sha256。"
        ),
    )
    md_file_path: str = Field(
        ...,
        description=(
            "目标笔记 markdown 的 vault 相对路径，如 items/vocab/aimai--01JZABD123.md。"
            "图片将复制到其同名 .assets 目录下。"
        ),
    )
    slug_hint: str = Field(
        ...,
        description=(
            "从 analyze_image 结果（ImageAnalysis：content_type / text / knowledge_points）"
            "提炼的 1-3 个英文关键词，用于生成可读的图片文件名。"
        ),
    )


def make_copy_session_image_tool(
    image_store: "ImageStore",
    target_lang: str,
) -> StructuredTool:
    """工厂函数：创建 copy_session_image_to_vault 工具，绑定特定 ImageStore 与目标语言。

    target_lang 为写入的 vault 语言（Chat Agent 为 profile.target_language，
    Memory Writer 为 entry.lang）。
    """

    @tool("copy_session_image_to_vault", args_schema=_CopySessionImageArgs)
    @log_tool_call("copy_session_image_to_vault")
    async def copy_session_image_to_vault(
        src_resource_sha256: str,
        md_file_path: str,
        slug_hint: str,
    ) -> str:
        """把聊天 session 中某张已上传图片复制到目标笔记 markdown 的 .assets 目录，
        返回可在 markdown 正文直接使用的相对引用路径。

        markdown 嵌入格式：![<alt>](<markdown_relative_path>)。图片只支持
        image/jpeg / image/png / image/webp。
        """
        from ..image.image_store import _MIME_EXT, save_vault_image, slugify

        data = image_store.read_bytes(src_resource_sha256)
        asset = image_store.get(src_resource_sha256)
        if data is None or asset is None:
            logger.warning(
                "copy_session_image_to_vault: no bytes for src=%s (registry empty?)",
                src_resource_sha256,
            )
            return json.dumps(
                {
                    "ok": False,
                    "error": f"image bytes unavailable for {src_resource_sha256}",
                },
                ensure_ascii=False,
            )

        mime_type = asset.mime_type
        ext = _MIME_EXT.get(mime_type, "bin")
        slug = slugify(slug_hint)
        stem = f"{slug}-{src_resource_sha256[:8]}"

        md_dir = posixpath.dirname(md_file_path)
        mdname = posixpath.basename(md_file_path)
        if mdname.endswith(".md"):
            mdname = mdname[:-3]
        assets_dir = f"{mdname}.assets"
        if md_dir:
            vault_rel_path = f"{md_dir}/{assets_dir}/{stem}.{ext}"
        else:
            vault_rel_path = f"{assets_dir}/{stem}.{ext}"

        try:
            save_vault_image(
                target_lang,
                vault_rel_path,
                data,
                mime_type,
                src_resource_sha256=src_resource_sha256,
            )
        except ValueError as exc:
            logger.warning(
                "copy_session_image_to_vault failed for src=%s: %s",
                src_resource_sha256, exc,
            )
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

        markdown_relative_path = f"{assets_dir}/{stem}.{ext}"
        return json.dumps(
            {
                "ok": True,
                "markdown_relative_path": markdown_relative_path,
                "vault_rel_path": vault_rel_path,
                "mime_type": mime_type,
            },
            ensure_ascii=False,
        )

    return copy_session_image_to_vault
