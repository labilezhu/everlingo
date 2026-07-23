# ref: chat-agent-spec.md — Agent 实现
# 主要实现在 MainAgent。产品文档中的"词典老师"、"翻译老师"均由同一个 langchain agent 实现。
# ref: /docs/impl-spec/chat-agent-spec.md

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)

from ..gateway.channels.channel import ChannelMetadata
from ..gateway.session_events import SystemNotice
from ..llm import create_agent, create_llm
from ..mem.agents.mem_entries import MemoryEntry
from ..mem.agents.mem_writer_mcp_client import (
    CHAT_AGENT_WANTED_TOOLS,
    IndexerOfflineError,
    _call_compile_prompt,
    mcp_vault_connection,
)
from ..models import LANGUAGES, UserProfile
from ..setting import load_profile, load_user_doc, prompt_input_mtime
from ..tools.conf_manager import get_config_version
from ..tools.tools import build_tools
from ..utils.md_prompt_compiler import shift_headings

import logging

logger = logging.getLogger(__name__)

# ── Retryable LLM errors ────────────────────────────────────────────
_RETRYABLE_LLM_ERRORS = (
    json.JSONDecodeError,
    httpx.HTTPError,
    InternalServerError,
    RateLimitError,
    APITimeoutError,
    APIConnectionError,
)

_NON_RETRYABLE_LLM_ERRORS = (
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    UnprocessableEntityError,
)


async def _invoke_llm_with_retry(
    agent: "CompiledStateGraph",
    messages: list,
    max_retries: int = 2,
    base_delay: float = 1.0,
) -> dict | None:
    """调用 LLM agent 并自动重试瞬态错误。

    成功 → 返回 response dict。
    重试耗尽 → 返回 None（调用方据此降级为友好提示）。
    永久性错误 → 透传异常。
    """
    last_exception: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await agent.ainvoke({"messages": messages})
        except _NON_RETRYABLE_LLM_ERRORS:
            raise
        except _RETRYABLE_LLM_ERRORS as e:
            last_exception = e
            if attempt < max_retries:
                delay = base_delay * (2**attempt)
                logger.warning(
                    "LLM invoke failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1,
                    max_retries + 1,
                    delay,
                    e,
                )
                await asyncio.sleep(delay)

    logger.exception(
        "agent.ainvoke failed after %d retries: %s",
        max_retries,
        last_exception,
    )
    return None


# ── Tool factories (bind instance state via closure) ────────────────
from ..tools.memory_writer_action import make_memory_writer_action_tool
from ..tools.request_memory_extract import make_request_memory_extract_tool

@dataclass
class MessageEvent:
    """从 Channel 收到的消息的规范化表示。

    ref: /docs/impl-spec/chat-agent-spec.md
    """

    # 消息正文
    text: str

    # 原始 Channel 数据
    raw_message: Any = None
    message_id: Optional[str] = None

    # 回复上下文
    reply_to_message_id: Optional[str] = None
    reply_to_text: Optional[str] = None

    # 时间戳
    timestamp: datetime = field(default_factory=datetime.now)


def _demote_headings(text: str) -> str:
    """将 markdown 标题降两级，确保低于 system prompt 中外围的 '##' 标题层级。

    ref: chat-agent-spec.md — USER.md 标题层级处理
    """
    return re.sub(r'^(#+)\s', r'##\1 ', text, flags=re.MULTILINE)


def _lang_display_name(code: str) -> str:
    return LANGUAGES.get(code, code)


def _get_memory_writer():
    """延迟导入 gateway 模块级 memory_writer 单例。

    延迟导入避免 main -> gateway -> agent -> main 循环 import；
    gateway 模块 import agent 时 _get_memory_writer 尚未被调用。
    """
    from ..gateway.gateway import memory_writer
    return memory_writer


# ref: docs/impl-spec/memory-extract-agent-spec.md — "轮"的定义 & 为什么分离 new / context
# 1 轮 = 1 个 HumanMessage + 其后到下一个 HumanMessage 之前的所有 AIMessage / ToolMessage。
# context_messages 取最近最多 19 轮（不含本轮），仅供生成 conversation_context。
# new_messages = 自上次 extract 游标以来新增的所有 messages，是唯一抽取来源。
_CONTEXT_TURNS_LIMIT = 19


def _tail_recent_turns(messages: list, limit: int = _CONTEXT_TURNS_LIMIT) -> list:
    """从 messages 尾部取最近 limit 个 user turn。

    1 turn = 1 HumanMessage + 其后到下一个 HumanMessage 之前的所有 AIMessage/ToolMessage。
    `_messages` 已排除注入的 SystemMessage；ToolMessage 必须保留。

    用于 context_messages（背景上下文）截断，不含本轮（调用方负责切片）。
    """
    # 收集所有 HumanMessage 的索引
    human_indexes = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    if len(human_indexes) <= limit:
        return list(messages)
    # 取最近 limit 个 turn 的起点：第 (len-limit) 个 HumanMessage 位置
    start = human_indexes[len(human_indexes) - limit]
    return list(messages[start:])


from datetime import timezone, timedelta

_GMT8 = timezone(timedelta(hours=8))


def _now_gmt8_str() -> str:
    """GMT+8 时间戳字符串，格式 yyyy-mm-dd HH:MM:SS。"""
    from datetime import datetime
    return datetime.now(_GMT8).strftime("%Y-%m-%d %H:%M:%S")


def _render_context_messages(messages) -> str:
    """把 messages 序列化为 LLM 可读的多行文本。

    按发言者与内容线性展开，保留 ToolMessage（查词/翻译工具结果是事实来源）。
    """
    lines: list[str] = []
    for m in messages:
        role = getattr(m, "type", "") or m.__class__.__name__
        content = getattr(m, "content", "") or ""
        if isinstance(content, list):
            content = str(content)
        lines.append(f"[{role}] {content}")
    return "\n".join(lines)


def _build_system_prompt(
    profile: UserProfile, user_doc: str = "", channel_metadata: ChannelMetadata | None = None,
    vault_available: bool = False, envelope_spec_content: str | None = None,
) -> str:
    """构建统一的 Agent system prompt，整合词典老师和翻译老师的功能。

    ref: /docs/impl-spec/chat-agent-spec.md — _build_system_prompt
    ref: /docs/product/pro-chatbot.md — 用户意图分析 & 用户意图响应
    """
    interface_lang = _lang_display_name(profile.language.interface_language)
    target_lang = _lang_display_name(profile.language.target_language)

    prompt = f"""你是 EverLingo 语言学习助手，你的名字叫 "小记"，头像是: 🐹。
你主要功能是针对用户的个性化偏好，解答用户在 {target_lang} 语言方面的问题。教学时，回复或发送消息给用户时，要充分考虑**用户熟识的语言是：{interface_lang} **。
处理每次用户消息的主要的流程是： 分析当前会话消息和历史消息 -> 识别用户意图(当最近系统消息未指定`对话模式`时) -> [可选:必要时调用提供的 tools] -> 作出友好与实用的回答。
你的记忆有两部分组成：
- 个性化偏好 (USER.md) ，支持读写，已经为你提供读写工具
- 目标学习语言({target_lang}) 的相关笔记(知识点)。



## 术语
先定义下面将使用的术语

### 语言
- 语言代码：`en` ： `英语`
- 语言代码：`ja` ： `日本語`
- 语言代码：`zh-CN` ： `简体中文`
- 语言代码：`fr` ： `法语`
- 语言代码：`de` ： `德语`
- `target_lang`: 用户的`目标学习语言`
- `interface_lang`: 用户的`界面语言`
- `single_word` : 如果 {target_lang} 是 `英语` 时为1个单词，是 `简体中文` 时为一个中文词语，其它语言也如此类推。
- `user_message_lang`： 你从用户最近的一条消息去识别出消息主要使用的语言
- `src_lang`： 要查词或翻译的原语言，一般同 `user_message_lang`
- `dest_lang`： 要查词或翻译输出的目标语言。一般默认是 {interface_lang}。 但如果 {interface_lang} 与 `src_lang` 相同时，应为  {target_lang}。 无论如何，`dest_lang` 不能与 `src_lang` 相同。

## 基本配置
当前生效配置包括：
- 界面语言(interface_lang): {interface_lang}
- 目标学习语言(target_lang): {target_lang}

## 个性化偏好 USER.md 配置
用户表达个性化偏好的自由 markdown 格式文件，内容可以包括：职业、爱好、性别、地区、年龄、学习目标、释义偏好、翻译偏好等。
下文统一叫 `USER.md` 。 在与用户交互时，不要用 USER.md 这个词，要说 “个性化偏好设置”。

如没有系统消息指定 `对话模式`，即自由对话时，如果用户表现出个性化偏好，可适当引导用户设置更新 USER.md。

"""

    # 用户自由偏好笔记 (USER.md)。由用户以自由文本维护，可由 Agent 通过 user_doc 工具更新。
    # ref: DOMAIN.md — 用户自由偏好笔记 (USER.md)
    if user_doc.strip():
        prompt += f"""
## 个性化偏好 (USER.md)
以下为用户以自由文本记录的个性化偏好，请在查词/翻译/答疑时予以考虑。
仅使用其中与当前任务相关的部分，不要机械复述。

---
{_demote_headings(user_doc.strip())}
---
"""

    # ref: docs/impl-spec/chat-agent-spec.md — 结构化用户输入（envelope）
    # envelope schema 通过 MCP compile_prompt 从 vault 运行期加载，shift_headings(+2) 后注入。
    envelope_section = r"""

## 结构化用户输入（envelope）
用户消息始终被 <envelope>...</envelope> 标签包裹，标签内是 JSON。

"""
    if envelope_spec_content:
        envelope_section += shift_headings(envelope_spec_content.strip(), offset=2) + "\n\n"

    prompt += envelope_section + f"""

## 用户意图分类

分析判断用户意图，然后作出响应。

## 用户意图识别

**envelope.task 的作用:**
envelope 的 `task` 字段表达用户指定的任务（`translate` / `look_up` / `none`）
已经的 `task`：
- `look_up` 偏向查单词
- `translate` 偏向翻译
- `none` 不影响意图识别。

当 task=look_up 且 chat.message 为空且 selection.text 为空时，视为"延续上一轮笔记话题"：
不要回复"未收到输入"，应基于对话历史继续推进相关工作（如读取/编辑上一轮提到的笔记）。

`用户意图类型` 按识别优先级从高到低分为：
1. 查单词
2. 翻译
3. 语言学习问题智能问答
4. 管理 USER.md
5. 管理基本配置
6. 未识别输入
7. 笔记读取和浏览
8. 抽取对话内容到笔记
9. 笔记删除
10. 笔记编辑

以下说明意图识别的方法。使用 LLM 对意图进行识别。根据 chatbot session 的历史消息上下文，用户的最近消息，识别用户意图。

#### 1. 查单词
**判定条件**：
而消息本身在 `user_message_lang` 语言里，是一个 `single_word`

#### 2. 翻译
**判定条件**：
你从用户消息判断意图是明确地要翻译文本，而不是查询单词
OR
`user_message_lang` 识别为 {target_lang} 语言文本，且输入由多个 `single_word` 组成

#### 3. 语言学习问题智能问答
**判定条件**：
你从用户消息判断是一个语言学习的问题，但不能匹配到已知的 `用户意图类型` 。但你有信心解答这个问题。

#### 4. 管理 USER.md
**判定条件**：
- 用户询问当前 USER.md（如"我的个性设置是什么"）
- 用户要求修改 USER.md（如"我是个程序员"）
- 用户要求修改 USER.md 如"词典释义时，加入小故事"）

#### 5. 管理基本配置
**判定条件**：
- 用户询问当前设置（如"我的配置是什么"）
- 用户要求修改设置（如"请你说中文"）
- 用户要求修改设置（如"我要学习英语"）

#### 6. 未识别输入
**判定条件**：
非语言学习相关的询问


## 用户意图响应

规则：用 {interface_lang} 作为主语言回复用户消息， `dest_lang` 与 {interface_lang} 为不同语言时除外。

### 查单词
查词输出要求最少有以下信息：
- 用 `dest_lang` 语言表达的`single_word`语义说明

个性化增加：
1. 根据 `用户自由偏好笔记 (USER.md)` 提供个性化的释义。只使用其中与该词相关的偏好内容。
2. 在 `笔记 Vault` 中找一下有没有高度相关的笔记，如果有，结合笔记回复用户（要在消息中说明信息来源于标题为xyz的笔记）。可以用 vault_mcp_search 、 vault_mcp_read 工具查找和加载相关笔记。

### 翻译
翻译输出使用 `dest_lang` 语言 。适当地根据 `用户自由偏好笔记 (USER.md)` 个性化。只使用其中与本次翻译相关的偏好内容。

- 在 `笔记 Vault` 中找一下有没有高度相关的笔记，如果有，结合笔记回复用户（要在消息中说明信息来源于标题为xyz的笔记）。可以用 vault_mcp_search 、 vault_mcp_read 工具查找和加载相关笔记。
- 标注翻译中值得注意的句式或短语
- 如果有多种译法，列出备选方案并说明差异
- 提供学习建议（如语法点、常见搭配等）


### 管理基本配置

**响应要求**：
使用 conf_manager 工具集中的函数：
- get_config: 查询当前配置
- set_config: 修改配置
- get_schema: 获取配置说明

### 管理 USER.md
用户自由偏好笔记 (USER.md) 的管理使用 user_doc 工具集：
- user_doc_get: 读取当前 USER.md 全文
- user_doc_set: 整体覆盖写入 USER.md。使用流程：先 user_doc_get 读取当前内容 → 在其基础上修改 → user_doc_set 写回完整内容。不要只写入片段。

用户表达个性化偏好（`USER.md`）时，应使用 user_doc 工具更新 USER.md，而非 set_config。
写入这个文件时，注意不要让文件超过 500 个字或单词。如果超过，要压缩提炼一下内容到少于 500 字后再写入。

### 未识别输入
**响应要求**：
礼貌地提示用户输入不明确，并给出使用示例：
- 查词示例：输入目标语言的单个词
- 翻译示例：输入目标语言的句子
- 管理 USER.md 示例
- 管理基本配置

"""

    # 注入 channel 能力与注意事项
    if channel_metadata is not None and channel_metadata.channel_prompt.strip():
        prompt += f"""
## 当前对话通道 (Channel) 能力与注意事项
{_demote_headings(channel_metadata.channel_prompt.strip())}
"""

    # 分级语音 prompt
    supports_mp3 = (
        channel_metadata is not None
        and "mp3" in channel_metadata.supported_sound_media_format
    )
    if supports_mp3:
        prompt += """
## 语音发送能力
当前对话通道支持发送 mp3 语音。当满足以下任一条件时，调用 `voice_speak` 工具发送语音：
1. 用户在「个性化偏好设置」中表达偏好发送语音
2. 用户在对话中显式要求发音/朗读/听一下

`voice_speak` 的内容优先级：
- 查词时：所查单词的发音
- 翻译时：目标短句的示范发音
- 仅当用户显式要求「朗读整段回复」时，才发送整段回复的语音

`voice_speak` 是异步的，调用后无需等待。可先正常给出文字回复，再决定是否调用 voice_speak。
因为语音发送给用户是异步的，这个语音消息和你回复的文本消息在用户端的顺序是不可预期的。所以不要在回复文本中说“以下是语音” 之类的话。说 “语音已发送” 就好 。
"""
    else:
        prompt += """
## 语音发送能力
当前对话通道不支持语音消息。若用户要求发送语音/朗读/发音，请用文字回复：「当前通道不支持语音，请在微信等支持语音的通道使用。」
"""

    # 记忆库只读访问（vault 工具）
    if vault_available:
        prompt += """
## 笔记 Vault / 知识库 

笔记 Vault / 知识库，是由 markdown 文件、结构化目录组成的 memory vault。 用于记录用户的语言学习事件和语言知识点。
在你考虑发起 笔记 Vault 相关的任何动作前，你必须先了解 vault 结构。如果你不了解 vault 结构，必须先 vault_mcp_read(path="spec/vault_spec.md") 学习 vault 规范。 `spec/vault_spec.md` 文件链接到其它子规范 md 文件，请按需要读取。

### 笔记读取和浏览

当用户明显要查询过往笔记/记忆时（如「我记过 xxx 吗」「查我笔记里关于 xxx 的」），这就是 `笔记读取和浏览` 意图
可使用 vault 工具：
"vault_mcp_read", "vault_mcp_ls", "vault_mcp_find", "vault_mcp_search", "vault_mcp_grep", "vault_mcp_list_tags"

#### 笔记的 search
笔记的 vault_mcp_search 工具返回的 hits 中的 snippet 如果没有用户查询的信息。不要简单回复用户说找不到。应该用 vault_mcp_read 加载前 3 个 hit 的 file_path 文件内容。阅读后再回答用户搜索结果。


### 抽取对话内容到笔记

如用户要求你记住一个知识点，或要求你记录笔记，这就是 `抽取对话内容到笔记` 意图。

#### 何时是 `抽取对话内容到笔记` 意图

1. **用户明确要求记住**：用户说"记住 / 记下 / 帮我记"某知识点时 —— entries 中 `why_want_to_save_memory` 设为 `"用户明确要求记住知识点"`
2. **纠正事项**：你发现并纠正了用户未预期的目标学习语言错误 —— entries 中 `why_want_to_save_memory` 设为 `"纠正事项"`
3. **其他你觉得值得记录的情形** —— entries 中 `why_want_to_save_memory` 设为 `"Chat Agent 判定"`

#### 何时不是 `抽取对话内容到笔记` 意图

- 与目标学习语言无关的闲聊
- 纯查词或翻译，没有纠正也没有显式要求记住
- 用户偏好类内容（应通过 user_doc 工具写入 USER.md）
- 琐碎/显而易见的信息
- 单条消息文本超过 1000 字时，该消息内容不作为知识点的事实来源

#### 执行 `抽取对话内容到笔记` 前必须

- 保证之前的历史消息已经产出过该知识点的实际内容（释义/解释/用法/举例），否则必须在本轮回复中产出。
- 因为，这些产出是下游 Memory Writer Agent 生成 conversation_context 与笔记正文的唯一事实来源

#### 当需要执行 `抽取对话内容到笔记` 时，按以下流程操作
1. 先调用 `vault_mcp_read(path="spec/memory_extract_output_spec.md")` 加载 entries 输出规范与字段说明
2. 按规范构造 entries，调用 `request_memory_extraction(entries=[...])`
3. 回复用户：已提交后台笔记请求
4. 下游 Memory Writer Agent 会异步将 entries 写入笔记库。你不需要直接调用读写笔记的工具


### 笔记删除

用户可以要求你删除已有的笔记条目（知识点文件）。

#### 操作流程

1. **定位文件**：
   - 优先从对话历史中推断 file_path（如 Memory Writer 通知的 updated_files，或之前定位过的文件）
   - 推断失败时，用 vault_mcp_search 搜索 top 4，逐一 vault_mcp_read 确认最匹配的文件
   - 定位到文件后，vault_mcp_read 读取其 frontmatter 获取 `title`(`标题`) 和 `type`(`知识类型`)

2. **必须确认**：
   - 执行删除前，必须向用户确认目标笔记的 `title` 和 `type`
   - 确认格式示例：「请确认：目标笔记 标题:「曖昧」, 知识类型:词汇, 文件:items/vocab/ufo.md 对吗？」
   - 用户确认后才可调用 memory_writer_action 工具
   - 用户否认并提供新提示 → 重新定位（回到步骤 1）
   - 用户取消 → 不执行

3. **调用工具**：
   - 删除：memory_writer_action(operation="delete", file_path="...")

4. **转告结果**：
   - 工具返回后，如实告知用户操作结果

#### 约束

- **禁止**在未确认的情况下调用 memory_writer_action
- **禁止**凭空编造 file_path；必须来自定位步骤

### 笔记编辑

用户可以要求你编辑已有的笔记条目（知识点文件）的正文和部分 Markdown Frontmatter 字段。

#### 可编辑与不可编辑的 Frontmatter 字段

以下字段 **不允许修改**（即使你传入新值，服务端也会以原文件为准）：
ulid / slug / type / created_at / timestamp / schema_version / first_seen / last_seen / seen_count

以下字段 **允许修改**：
title / description / description_in_target_lang / tags（以及其他非上述保护字段的键）

#### 操作流程

1. **定位文件**：
   - 优先从对话历史中推断 file_path（如 Memory Writer 通知的 updated_files，或之前定位过的文件）
   - 推断失败时，用 vault_mcp_search 搜索 top 4，逐一 vault_mcp_read 确认最匹配的文件
   - 定位到文件后，vault_mcp_read 读取其 frontmatter 获取 `title` 和 `item_type`

2. **必须确认**：
   - 执行编辑前，必须向用户确认目标笔记的 `title` 和 `item_type`
   - 确认格式示例：「请确认：目标笔记 标题:「曖昧」, 知识类型:词汇, 文件:items/vocab/ufo.md 对吗？」
   - 确认时仅确认旧 title ， 编辑时允许将 title 改为新值
   - 用户确认后才可 执行编辑操作
   - 用户否认并提供新提示 → 重新定位（回到步骤 1）
   - 用户取消 → 不执行

3. **执行编辑操作**：
   1. 必须调用 vault_mcp_read(path=file_path) 工具，加载最新原文件
   2. 在内存中按用户要求编辑文件：
      - **正文**：去除 markdown frontmatter 部分后，按用户要求修改正文
      - **Frontmatter**：保留保护字段（ulid/slug/type/created_at/timestamp/schema_version/first_seen/last_seen/seen_count）的原值不变，按用户要求修改可编辑字段（title/description/description_in_target_lang/tags 等）
   3. 调用 memory_writer_action(operation="edit", file_path="...", body="<新正文>")
      - 如需同时修改 frontmatter，传入 frontmatter="<完整 frontmatter YAML 文本>"
      - frontmatter 参数中的保护字段值会被服务端忽略，以原文件为准，你可放心按完整模板传入
   4. 工具会调用 Memory Write Agent 修改文件。

4. **转告结果**：
   - 工具返回后，如实告知用户操作结果。若 title 已被编辑，告知用户新 title。

#### 约束

- **禁止**在未确认的情况下调用 memory_writer_action
- **禁止**凭空编造 file_path；必须来自定位步骤
- 调用 memory_writer_action 时 body 参数必须是完整正文，不能是片段

"""
    else:
        prompt += """
## 记忆库访问
记忆库暂不可用，请告知用户稍后再试。
"""

    # 系统事件通知
    prompt += """
## 系统事件通知
偶尔你会收到以 `[系统通知]` 开头的 HumanMessage。这不是用户真实输入，
不要按「用户意图分类」处理。请以本节的规则为准。

### Memory Writer 通知
当 Memory Writer 成功写入记忆库(笔记入库)后会通知你，通知包含：
- updated_files：本次更新的 vault 文件路径
- update_summary：更新内容概述
- title：知识点标题
- lang：目标学习语言

收到通知后，根据 USER.md 中用户的偏好判断：
- 用户未指定笔记入库通知偏好时 → 简短确认即可，如：
    ```
    📝后台笔记成功记录✅：
    - 标题:「曖昧」
    - 知识类型: 词汇
    - 文件:items/vocab/ufo.md
    - 更新概要： 加入一个新的示例句子
    ```
- 用户指定了笔记入库通知偏好时 → 按用户偏好回复消息给用户。如需详情可用 vault_mcp_read(path=文件路径) 读取文件
"""

    return prompt


class MainAgent:
    """EverLingo 主 Agent。

    产品文档中的"词典老师"、"翻译老师"均由同一个 langchain agent 实现。
    ref: /docs/impl-spec/chat-agent-spec.md
    """

    def __init__(
        self,
        profile: UserProfile,
        channel_metadata: ChannelMetadata,
        channel: Any,
        session_id: Optional[str] = None,
    ) -> None:
        self._channel_metadata = channel_metadata
        self._channel = channel
        self._profile = profile
        self._llm = create_llm()
        self._target_lang = profile.language.target_language
        # 基础工具（不含 vault），vault 工具在 _ensure_mcp_stream 后追加
        self._tools_base = build_tools(channel_metadata, channel)
        self._tools: list = []
        # MCP 长连接管理
        self._mcp_ctx: Any = None
        self._mcp_session: Any = None
        self._vault_tools: list = []
        # Agent 懒创建；首次 ainvoke 时通过 _refresh_agent_if_needed 构建
        self._agent: Any = None
        # 记录构建时的配置版本与文件 mtime，用于检测是否需要重建 agent
        # ref: chat-agent-spec.md — system prompt 维护
        self._config_version: tuple = get_config_version()
        self._prompt_mtime: tuple = prompt_input_mtime()
        # Agent 的消息历史，支持多轮会话
        self._messages: list = []
        # extract 游标：已提交过 extract 的 _messages 长度。
        # 每轮 invoke 末尾切片 new/context 后推进。
        # 即使故障也推进（可接受丢失），避免失败轮次被重抽。
        self._extract_cursor: int = 0

        # request_memory_extraction 工具累积的 entries drafts。
        # invoke 末尾据此构造 MemoryEntry 并入队 Writer。
        self._pending_drafts: list = []

        # session_id 为 None 时（极少数测试场景）生成稳定 id。
        self._session_id = session_id or "no-session-id"

    def _add_pending_drafts(self, drafts: list) -> None:
        """request_memory_extraction 工具回调：累积 drafts。

        工具在 LLM 多步循环中被调用，此时 invoke 尚未结束、
        new_messages 切片未就绪。工具只累积 drafts，不直接入队。
        一轮内多次调用工具会顺序累积所有 drafts。
        """
        self._pending_drafts.extend(drafts)

    async def _ensure_mcp_stream(self) -> None:
        """懒打开到 Vault MCP Server 的长连接，配置会话 lang，加载只读工具。

        已打开时幂等。Indexer 离线等失败由内部 catch，设 _vault_tools=[]。
        """
        if self._mcp_ctx is not None:
            return
        try:
            ctx = mcp_vault_connection(self._target_lang, wanted_tools=CHAT_AGENT_WANTED_TOOLS)
            session, tools = await ctx.__aenter__()
            self._mcp_ctx = ctx
            self._mcp_session = session
            self._vault_tools = tools
            logger.info("vault MCP stream opened for lang=%s", self._target_lang)
        except IndexerOfflineError as e:
            logger.warning("vault MCP offline: %s", e)
            self._vault_tools = []
        except Exception as e:
            logger.warning("vault MCP init failed: %s", e)
            self._vault_tools = []

    async def _close_mcp_stream(self) -> None:
        """关闭 MCP 长连接。"""
        if self._mcp_ctx is not None:
            await self._mcp_ctx.__aexit__(None, None, None)
            self._mcp_ctx = None
            self._mcp_session = None
        self._vault_tools = []

    async def aclose(self) -> None:
        """关闭 MCP 长连接（Session.run 退出时调用）。"""
        await self._close_mcp_stream()

    # ── Agent 重建 ──────────────────────────────────────────────

    async def _refresh_agent_if_needed(self) -> None:
        """检查配置版本或依赖文件 mtime，若变化则重建 agent 以刷新 system prompt。

        触发条件（任一即可）：
        - self._agent 尚为 None（首次 ainvoke）
        - prompt 版本号变化（set_config / user_doc_set 被调用过）
        - everlingo.yaml 或 USER.md 的 mtime 变化（外部编辑器修改）

        同时管理 MCP 长连接：target_lang 变化时关闭旧 stream，下次 ainvoke
        时 _ensure_mcp_stream 自动用新 lang 重开。

        ref: /docs/impl-spec/chat-agent-spec.md — _build_system_prompt 依赖配置
        """
        current_version = get_config_version()
        current_mtime = prompt_input_mtime()
        if self._agent is not None and current_version == self._config_version and current_mtime == self._prompt_mtime:
            return

        profile = load_profile()

        # target_lang 变化 → 关闭旧 MCP stream（新 lang 由 _ensure_mcp_stream 自动使用）
        if profile.language.target_language != self._target_lang:
            await self._close_mcp_stream()
            self._target_lang = profile.language.target_language

        # 确保 MCP stream 已打开
        await self._ensure_mcp_stream()

        # 通过 MCP compile_prompt 从 vault 加载 envelope_spec.md（与 Memory Writer 一致）
        # vault 离线时不兜底，envelope_spec_content 为 None
        envelope_spec_content: str | None = None
        if self._mcp_session is not None:
            try:
                envelope_spec_content = await _call_compile_prompt(
                    self._mcp_session, "spec/envelope_spec.md"
                )
            except (IndexerOfflineError, RuntimeError) as e:
                logger.warning(
                    "failed to load envelope_spec via MCP compile_prompt: %s", e
                )

        user_doc = load_user_doc()
        extract_tool = make_request_memory_extract_tool(self._add_pending_drafts)
        memory_writer = _get_memory_writer().get_agent()
        memory_writer_tool = make_memory_writer_action_tool(
            memory_writer=memory_writer,
            target_lang=self._target_lang,
            interface_lang=profile.language.interface_language,
            chat_session_id=self._session_id,
            channel_name=self._channel_metadata.name,
        )
        self._tools = list(self._tools_base) + [extract_tool, memory_writer_tool] + list(self._vault_tools)
        self._agent = create_agent(
            self._llm,
            tools=self._tools,
            system_prompt=_build_system_prompt(
                profile, user_doc, self._channel_metadata,
                vault_available=bool(self._vault_tools),
                envelope_spec_content=envelope_spec_content,
            ),
        )
        self._config_version = current_version
        self._prompt_mtime = current_mtime

        logger.info(
            "agent %s: version %s, mtime %s, vault=%s",
            "created" if self._agent is not None and self._mcp_ctx is not None else "refreshed",
            current_version, current_mtime, bool(self._vault_tools),
        )

    async def ainvoke(self, input_msg: MessageEvent) -> list[MessageEvent]:
        """处理用户消息，返回 Agent 的回复列表（每条对应一个消息气泡）。

        当 LLM 在工具调用循环中产生多个 AIMessage（例如「翻译并朗读」场景：
        第一条 AIMessage 含翻译正文 + tool_calls，第二条 AIMessage 为空/简短确认），
        每个非空 AIMessage.content 会作为一个独立的 MessageEvent 返回，由 Session
        逐条调用 channel.send()，在微信等通道形成多个消息气泡。
        ToolMessage 不计入回复（其内容如 "voice scheduled" 是工具结果，
        语音已由 voice_speak 工具异步直发 channel）。

        ref: /docs/impl-spec/chat-agent-spec.md — 用户意图的执行与回复响应
        """
        # 若 agent 尚未创建或配置被修改过，先重建 agent 以刷新 system prompt
        # 同时确保 MCP 长连接已打开
        await self._refresh_agent_if_needed()

        text = input_msg.text.strip()

        # ── 构建 LLM 输入消息列表 ─────────────────────────────
        messages_for_llm = list(self._messages)
        messages_for_llm.append(HumanMessage(content=text))
        # 将用户消息写入持久化历史（不含模式提示）
        self._messages.append(HumanMessage(content=text))

        # ── 调用 LLM（含瞬态重试） ────────────────────────────
        try:
            response = await _invoke_llm_with_retry(self._agent, messages_for_llm)
        except Exception as e:
            logger.exception("ainvoke: LLM call failed")
            return [MessageEvent(text=f"出错了，请稍后重试: {e}")]
        if response is None:
            return [MessageEvent(text="AI 服务暂时不可用，请稍后重试 (已自动重试 2 次)")]

        # 持久化 AI 回复
        # 含 ToolMessage，供多轮对话中 LLM 上下文使用
        new_messages = response["messages"][len(messages_for_llm):]
        self._messages.extend(new_messages)

        # 每个非空 AIMessage.content 作为一个独立 MessageEvent 返回
        replies = [
            MessageEvent(text=m.content)
            for m in new_messages
            if isinstance(m, AIMessage) and m.content and m.content.strip()
        ]

        # ── 直接构造 MemoryEntry 入队 Writer（异步，不阻塞回复） ──
        # 由 Chat Agent 通过 request_memory_extraction 工具显式触发。
        # new_messages = 自上次 extract 游标以来新增的 messages
        # context_messages = 游标之前的最近 19 轮（仅供 conversation_context）
        # 游标始终推进；未触发时本轮自然并入未来 context_messages。
        if self._pending_drafts:
            drafts = self._pending_drafts
            self._pending_drafts = []
            new_msgs = list(self._messages[self._extract_cursor:])
            ctx_msgs = _tail_recent_turns(
                self._messages[:self._extract_cursor]
            )
            self._extract_cursor = len(self._messages)
            new_text = _render_context_messages(new_msgs)
            ctx_text = _render_context_messages(ctx_msgs)
            ts = _now_gmt8_str()
            import uuid
            entries = [
                MemoryEntry(
                    entry_id=str(uuid.uuid4()),
                    timestamp=ts,
                    chat_session_id=self._session_id,
                    channel_name=self._channel_metadata.name,
                    lang=self._target_lang,
                    interface_language=self._profile.language.interface_language,
                    new_messages=new_text,
                    context_messages=ctx_text,
                    item_type=d.item_type,
                    why_want_to_save_memory=d.why_want_to_save_memory,
                    title=d.title,
                )
                for d in drafts
            ]
            logger.debug(
                "[ChatAgent] submit mem_entries to MemoryWriter: "
                "session=%s channel=%s count=%d entries=%s",
                self._session_id, self._channel_metadata.name,
                len(entries), [e.model_dump() for e in entries],
            )
            _get_memory_writer().enqueue(entries)
        else:
            # 未触发抽取：游标仍推进，本轮内容自然成为未来 context
            self._extract_cursor = len(self._messages)

        return replies

    async def ahandle_system_notice(self, notice: SystemNotice) -> list[MessageEvent]:
        """处理系统事件通知（如 Memory Writer 写入确认），LLM 中介。

        ref: session.md — 系统事件源
        通知以 `[系统通知]` 前缀的 HumanMessage 注入，走 LLM 决定是否告知用户及详情程度。
        跳过 extract（知识已被 Writer 写入，避免重复抽取）。
        """
        await self._refresh_agent_if_needed()

        files_str = ", ".join(notice.updated_files)
        notice_text = (
            f"[系统通知] Memory Writer 已更新记忆库：\n"
            f"- 知识点 title: {notice.title}\n - lang={notice.lang}\n"
            f"- 文件: {files_str}\n"
            f"- 概要: {notice.update_summary}\n"
            f"请根据用户偏好(USER.md)决定是否告知用户及详情程度。"
            f"若需详情可用 vault_mcp_read(path=文件路径) 读取文件。"
            f"若用户未表达希望收到通知，回复空内容。"
        )

        messages_for_llm = list(self._messages)
        notice_msg = HumanMessage(content=notice_text)
        messages_for_llm.append(notice_msg)
        self._messages.append(notice_msg)

        try:
            response = await self._agent.ainvoke({"messages": messages_for_llm})
        except Exception as e:
            logger.exception("ahandle_system_notice failed")
            return [MessageEvent(text=f"处理系统通知时出错: {e}")]

        new_messages = response["messages"][len(messages_for_llm):]
        self._messages.extend(new_messages)

        replies = [
            MessageEvent(text=m.content)
            for m in new_messages
            if isinstance(m, AIMessage) and m.content and m.content.strip()
        ]

        # 跳过 extract：知识已被 Writer 写入，重新抽取会重复
        self._extract_cursor = len(self._messages)

        return replies
