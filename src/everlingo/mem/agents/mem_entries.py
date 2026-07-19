# ref: docs/impl-spec/memory-writer-agent-spec.md — conversation memory entry 字段
# 知识点记忆流水线的数据结构定义。
# Chat Agent 构造 MemoryEntry 后直接入队 Memory Writer Agent。

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


# ── 类型别名声明的 Memory Entry 字段 ─────────────────────────────────

# `item_type` 仅使用 vault 规范定义的四种知识类型。
ItemType = Literal["vocab", "phrase", "grammar", "pragmatics", "others"]

# why_want_to_save_memory 枚举值：
# - "用户明确要求记住知识点" / "纠正事项" / "Chat Agent 判定"
WhySave = Literal["用户明确要求记住知识点", "纠正事项", "Chat Agent 判定"]


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
    item_type: ItemType = "others"
    why_want_to_save_memory: WhySave = "Chat Agent 判定"
    title: str = ""

    # delete/edit 专属字段
    file_path: str | None = None
    body: str | None = None
    frontmatter: str | None = None
