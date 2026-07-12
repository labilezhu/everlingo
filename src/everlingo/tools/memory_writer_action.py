from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langchain_core.tools import StructuredTool, tool
from pydantic import BaseModel, Field

from . import log_tool_call

if TYPE_CHECKING:
    from ..mem.agents.mem_writer_agent import MemoryWriterAgent

logger = logging.getLogger(__name__)


class _MemoryWriterActionArgs(BaseModel):
    operation: str = Field(
        ...,
        description='"delete": 删除笔记文件 | "edit": 编辑笔记文件正文',
    )
    file_path: str = Field(
        ...,
        description=(
            "相对 vault 根的文件路径，如 items/vocab/aimai--01JZABD123.md。"
            "必须以 items/ 开头，无前导 /"
        ),
    )
    body: str = Field(
        default="",
        description='operation="edit" 时必选。新 markdown 正文（不含 frontmatter YAML 元数据段）。',
    )


def make_memory_writer_action_tool(
    memory_writer: "MemoryWriterAgent",
    target_lang: str,
    interface_lang: str,
    chat_session_id: str,
    channel_name: str,
) -> StructuredTool:
    """工厂函数：创建 memory_writer_action 工具，绑定到特定 MainAgent 实例。

    工具内部创建 MemoryEntry 并通过 memory_writer.execute_action_async()
    同步调用 Memory Writer Agent。
    """

    @tool("memory_writer_action", args_schema=_MemoryWriterActionArgs)
    @log_tool_call("memory_writer_action")
    async def memory_writer_action(
        operation: str,
        file_path: str,
        body: str = "",
    ) -> str:
        """同步执行笔记删除或编辑。

        调用前必须已与用户确认目标笔记的 title 和 item_type。
        调用后等待 Memory Writer 完成操作并返回结果 JSON。
        """
        from datetime import datetime
        from uuid import uuid4

        from ..mem.agents.mem_entries import MemoryEntry

        entry = MemoryEntry(
            operation=operation,
            entry_id=str(uuid4()),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            chat_session_id=chat_session_id,
            channel_name=channel_name,
            user_intent="None",
            lang=target_lang,
            interface_language=interface_lang,
            file_path=file_path,
            body=body or None,
        )
        result = await memory_writer.execute_action_async(entry)
        import json

        return json.dumps(result, ensure_ascii=False)

    return memory_writer_action
