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
    写入前会把旧内容备份到 USER.md.bak（若旧文件存在）。成功后返回写入的内容。
    """
    user_doc_path = workspace.user_doc_path()
    # 备份旧内容（若存在）
    if user_doc_path.exists():
        bak_path = user_doc_path.with_suffix(".md.bak")
        bak_path.write_text(
            user_doc_path.read_text(encoding="utf-8"), encoding="utf-8"
        )

    save_user_doc(content)
    bump_prompt_version()

    return content
