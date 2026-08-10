from langchain_core.tools import tool

from .. import workspace
from ..setting import (
    bump_prompt_version,
    load_user_doc,
    save_user_doc,
)
from . import log_tool_call


@tool("user_doc_get")
@log_tool_call("user_doc_get")
def user_doc_get() -> str:
    """读取用户的自由文本偏好笔记 (USER.md) 全文。文件不存在时返回空串。"""
    return load_user_doc()


@tool("user_doc_set")
@log_tool_call("user_doc_set")
def user_doc_set(content: str) -> str:
    """整体覆盖写入用户的自由文本偏好笔记 (USER.md)。
    历史版本由 Memory Vault 版本控制（git）托管，详见 vault-version-control.md；
    不再写 USER.md.bak。成功后返回写入的内容。
    """
    save_user_doc(content)
    bump_prompt_version()

    return content
