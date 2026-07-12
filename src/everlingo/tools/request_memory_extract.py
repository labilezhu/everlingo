from typing import Callable

from langchain_core.tools import StructuredTool, tool
from pydantic import BaseModel, Field

from . import log_tool_call


class _RequestMemoryExtractArgs(BaseModel):
    reason: str = Field(
        ...,
        description="触发原因：user_explicit_request / correction / other",
    )
    note: str = Field(
        default="",
        description="可选语义提示，给下游 Extract Agent 参考，不指定具体 entries 内容",
    )


def make_request_memory_extract_tool(
    set_pending: Callable[[str, str], None],
) -> StructuredTool:
    """工厂函数：创建 request_memory_extraction 工具，绑定到特定 MainAgent 实例。

    工具执行体仅设置 pending 标记，不在工具调用循环内直接 submit ——
    实际 submit 由 MainAgent.invoke() 末尾统一处理，确保切片正确。
    """

    @tool("request_memory_extraction", args_schema=_RequestMemoryExtractArgs)
    @log_tool_call("request_memory_extraction")
    def request_memory_extraction(reason: str, note: str = "") -> str:
        """请求对本轮对话进行记忆抽取，将知识点异步写入记忆库。

        调用场景：
        - 用户明确要求记住知识点（如"记住 X"、"帮我记下 X"）
        - 你纠正了用户的目标学习语言错误且用户未预期到
        - 其他你觉得值得记录的情形

        调用前必须已在本轮回复中产出知识点的实际内容（释义/解释/用法/举例），
        因为这是下游 Extract Agent 抽取事实的唯一来源。

        调用后立即返回，抽取异步执行，不阻塞回复。
        """
        set_pending(reason, note)
        return "memory extraction requested"

    return request_memory_extraction
