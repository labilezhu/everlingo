from typing import Callable

from langchain_core.tools import StructuredTool, tool
from pydantic import BaseModel, Field

from . import log_tool_call


class _MemoryEntryDraft(BaseModel):
    """LLM 应负责生成的 entry 字段（系统字段由 MainAgent 代码补全）。"""

    item_type: str = Field(
        description="知识类型：vocab（单词） / phrase（短语） / grammar（语法点） / pragmatics（语用） / others（其他）",
    )
    why_want_to_save_memory: str = Field(
        description="为什么要记住：用户明确要求记住知识点 / 纠正事项 / Chat Agent 判定",
    )
    title: str = Field(
        description="使用界面语言，限一句话，描述本知识点。用于语义搜索和全文搜索。",
    )


class _RequestMemoryExtractArgs(BaseModel):
    entries: list[_MemoryEntryDraft] = Field(
        description="本轮对话中提取的知识点列表。每个 entry 含 item_type / why_want_to_save_memory / title。",
    )


def make_request_memory_extract_tool(
    add_drafts: Callable[[list], None],
) -> StructuredTool:
    """工厂函数：创建 request_memory_extraction 工具，绑定到特定 MainAgent 实例。

    工具执行体仅累积 drafts，不在工具调用循环内直接 submit ——
    实际构造 MemoryEntry 并入队 Writer 由 MainAgent.invoke() 末尾统一处理。
    """

    @tool("request_memory_extraction", args_schema=_RequestMemoryExtractArgs)
    @log_tool_call("request_memory_extraction")
    def request_memory_extraction(entries: list) -> str:
        """请求将本轮对话中的知识点异步写入记忆库。

        调用场景：
        - 用户明确要求记住知识点（如"记住 X"、"帮我记下 X"）
        - 你纠正了用户的目标学习语言错误且用户未预期到
        - 其他你觉得值得记录的情形

        调用前必须已在本轮回复中产出知识点的实际内容（释义/解释/用法/举例）。
        调用前应先 vault_mcp_read(path="spec/memory_extract_output_spec.md")
        了解 entries 字段结构与含义。

        调用后立即返回，写入异步执行，不阻塞回复。
        """
        add_drafts(entries)
        return "memory extraction requested"

    return request_memory_extraction
