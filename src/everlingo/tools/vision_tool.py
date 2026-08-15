# ref: docs/ADR/20260812-image-chat.md §12 / §22 / §29
# analyze_image 工具：Agent 获取图片理解结果的唯一路径（ToolMessage 模式）。
# 与 make_memory_writer_action_tool 同模式：工厂返回 StructuredTool，绑定特定 service。

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langchain_core.tools import StructuredTool, tool
from pydantic import BaseModel, Field

from . import log_tool_call

if TYPE_CHECKING:
    from ..image.vision_service import VisionService

logger = logging.getLogger(__name__)


class _AnalyzeImageArgs(BaseModel):
    src_resource_sha256: str = Field(
        ...,
        description=(
            "用户消息 envelope.chat.attachments[].src_resource_sha256 中的图片标识"
            "（上传时客户端计算的原始文件 hash）。"
        ),
    )


def make_vision_tool(service: "VisionService") -> StructuredTool:
    """工厂函数：创建 analyze_image 工具，绑定特定 VisionService 实例。"""

    @tool("analyze_image", args_schema=_AnalyzeImageArgs)
    @log_tool_call("analyze_image")
    async def analyze_image(src_resource_sha256: str) -> str:
        """分析用户在消息中上传的图片，返回结构化理解结果（ImageAnalysis JSON）。

        适用场景：用户消息 envelope 携带 chat.attachments（含图片）时，先调用本工具
        获取图片内容，再据此回答/讲解。返回 JSON 包含：
        content_type / language / text（接近原图的文字）/ structured_content（业务结构）
        / knowledge_points。
        """
        from ..image.models import ImageInput
        from ..image.vision_service import VisionServiceError

        try:
            analysis = await service.analyze(
                ImageInput(src_resource_sha256=src_resource_sha256)
            )
            return analysis.model_dump_json(ensure_ascii=False)
        except VisionServiceError as exc:
            # ADR §29：工具返回结构化降级提示而非抛异常中断会话。
            logger.warning("analyze_image degraded: code=%s err=%s", exc.code, exc)
            return (
                "抱歉，我暂时无法识别这张图片，请稍后再试或换个角度重新拍摄。"
                f"（{exc.code}）"
            )

    return analyze_image