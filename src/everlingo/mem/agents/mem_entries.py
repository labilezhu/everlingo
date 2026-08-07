# ref: docs/impl-spec/memory-writer-agent-spec.md — conversation memory entry 字段
# 知识点记忆流水线的数据结构定义。
# Chat Agent 构造 MemoryEntry 后直接入队 Memory Writer Agent。

from __future__ import annotations

from pydantic import BaseModel


# `item_type` 取值以 vault_spec.md 的 `知识类型` 定义为准（自由字符串，不由代码枚举）。
# why_want_to_save_memory 为自由文本：由 LLM 按界面语言生成一句「记住原因」，
# 程序不按枚举处理（见 i18n.md —— 界面语言相关内容由 LLM 依据 prompt 决定）。


class MemoryEntry(BaseModel):
    """完整的 conversation memory entry，与 memory-writer-agent-spec.md 对齐。

    Chat Agent 在 ainvoke() 末尾由代码构造此对象，入队 Memory Writer Agent。
    operation="delete" / "edit" 时由 Chat Agent 的 memory_writer_action 工具构造
    并同步调用 Writer。
    """

    # 操作类型："create"(默认) | "delete" | "edit"
    operation: str = "create"

    # 代码生成：uuid4
    entry_id: str
    # Extract 执行时刻，格式 yyyy-mm-dd HH:MM:SS，GMT+8
    timestamp: str
    # 会话元数据
    chat_session_id: str
    channel_name: str
    lang: str         # target_lang 语言代码
    interface_language: str  # 界面语言

    # 代码渲染的对话文本
    new_messages: str = ""
    context_messages: str = ""

    # LLM 生成（通过工具 args_schema 约束）
    item_type: str = "others"
    why_want_to_save_memory: str = ""
    title: str = ""

    # delete/edit 专属字段
    file_path: str | None = None
    body: str | None = None
    frontmatter: str | None = None
