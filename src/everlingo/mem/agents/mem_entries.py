# ref: docs/impl-spec/memory-extract-agent-spec.md — 输入/输出/数据结构
# ref: docs/impl-spec/memory-writer-agent-spec.md — conversation memory entry 字段
# 知识点记忆流水线共享的数据结构定义。
# Extract Agent 的输入与 LLM 结构化输出；Writer Agent（暂未实现）将消费同一份 MemoryEntry。

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional, Protocol

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field


# ── 输入规范 ──────────────────────────────────────────────────────────


@dataclass
class ExtractInput:
    """Memory Extract Agent 单次执行的结构化输入。

    ref: docs/impl-spec/memory-extract-agent-spec.md — 输入规范

    会话级元数据（chat_session_id / channel_name / target_lang / interface_lang）
    由 Extract Agent 实例持有，每轮 extract 复用，不放入 ExtractInput，
    保证输入可序列化、可测试，且与状态解耦。

    会话内 dedup 由 MainAgent 通过 extract 游标在输入侧完成（new/context 分离），
    Extract Agent 自身无状态。
    """

    # 本轮 MainAgent._intent_mode 快照：None=自动, "dict"=查词, "translate"=翻译
    intent_mode: Optional[str]

    # 本轮新增 messages（自上次 extract 游标以来）。
    # 唯一允许的抽取来源。通常含本轮 HumanMessage + 其后的 AIMessage / ToolMessage；
    # 必须保留 ToolMessage —— 查词/翻译工具返回是 mean_summary 的事实来源。
    new_messages: list[BaseMessage]

    # 背景上下文（不含本轮），最近最多 19 轮。
    # 仅供 LLM 生成 conversation_context 字段，禁止从中抽取知识点。
    context_messages: list[BaseMessage]


# ── 输出规范 ──────────────────────────────────────────────────────────


# 与 memory-writer-agent-spec.md 的 conversation memory entry 字段对齐。
# `item_type` 仅使用 vault 规范定义的四种知识类型。
ItemType = Literal["vocab", "phrases", "grammar", "pragmatics"]

# 本阶段 why_want_to_save_memory 仅允许两个枚举值（其余推迟到下一阶段）。
# ref: memory-extract-agent-spec.md — why_want_to_save_memory 枚举
WhySave = Literal["用户明确要求记住知识点", "纠正事项"]


class ExtractLLMOutput(BaseModel):
    """LLM 结构化输出 schema：只暴露 LLM 应负责生成的字段。

    其余字段（chat_session_id / entry_id / timestamp / channel_name /
    user_intent / lang）由 Extract Agent 在 post-process 阶段用实例属性与
    uuid4 / GMT+8 时间戳填充，LLM 不参与生成，避免不一致或幻觉。

    ref: docs/impl-spec/memory-extract-agent-spec.md — 输出规范 · 字段来源约定
    """

    entries: list["LLMGeneratedEntry"] = Field(
        default_factory=list,
        description="本轮筛选出的 memory entries；若无符合规则的知识点则为空列表",
    )


class LLMGeneratedEntry(BaseModel):
    """LLM 负责生成的 entry 子集（不含透传与系统生成字段）。"""

    item_type: ItemType = Field(
        description="知识类型：vocab / phrases / grammar / pragmatics",
    )
    why_want_to_save_memory: WhySave = Field(
        description=(
            "本阶段仅允许两个值：'用户明确要求记住知识点' / '纠正事项'。"
            "其余原因（推断用户需要记住 / 主动询问相关）推迟到下一阶段。"
        ),
    )
    headword: str = Field(
        description="知识点 keyword：单词时为单词本身，短语则原样写出",
    )
    mean_summary: str = Field(
        description=(
            "headword 的释义说明。"
            "本轮若 ToolMessage 存在（查词/翻译工具返回），必须基于其事实内容；"
            "不允许引入外部知识或 USER.md 偏好进行个性化改写。"
        ),
    )
    conversation_context: str = Field(
        description="对话上下文：用户在什么场景下查询/学习这个知识点",
    )


class MemoryEntry(BaseModel):
    """完整的 conversation memory entry，与 memory-writer-agent-spec.md 对齐。

    Extract Agent 在 LLM 输出上覆盖透传字段并补充 entry_id / timestamp 后得到此对象，
    转交给 Memory Writer Agent（当前 stub）。
    """

    # 代码生成：uuid4
    entry_id: str
    # Extract 执行时刻，格式 yyyy-mm-dd HH:MM:SS，GMT+8
    timestamp: str
    # 会话元数据（实例属性覆盖）
    chat_session_id: str
    channel_name: str
    user_intent: str  # "dict" / "translate" / "None"
    lang: str         # target_lang 语言代码
    # ref: docs/impl-spec/memory-writer-agent-spec.md — interface_language
    interface_language: str  # 界面语言

    # LLM 生成
    item_type: ItemType
    why_want_to_save_memory: WhySave
    headword: str
    mean_summary: str
    conversation_context: str


# ── Writer 转发协议 ───────────────────────────────────────────────────


class EntryWriterProtocol(Protocol):
    """Memory Writer Agent 异步写入队列接口。

    ref: docs/impl-spec/memory-extract-agent-spec.md — 异步执行
    Extract Agent 通过该接口把已生成 entries 转交给 Memory Writer Agent。
    本阶段 Writer 未实现，使用 gateway.memory_writer 的 log-only stub。
    """

    def enqueue(self, entries: list[MemoryEntry]) -> Any:
        ...
