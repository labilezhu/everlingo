# ref: agents-spec.md — Agent 实现
# 主要实现在 MainAgent。产品文档中的"词典老师"、"翻译老师"均由同一个 langchain agent 实现。
# ref: /docs/impl-spec/agents-spec.md

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from ..llm import create_agent, create_llm
from ..models import LANGUAGES, UserProfile
from ..setting import load_profile
from ..tools.conf_manager import get_config_version
from ..tools.tools import get_all_tools

import logging

logger = logging.getLogger("everlingo")

@dataclass
class MessageEvent:
    """从 Channel 收到的消息的规范化表示。

    ref: /docs/impl-spec/agents-spec.md
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


def _lang_display_name(code: str) -> str:
    return LANGUAGES.get(code, code)


def _build_system_prompt(profile: UserProfile) -> str:
    """构建统一的 Agent system prompt，整合词典老师和翻译老师的功能。

    ref: /docs/impl-spec/agents-spec.md — _build_system_prompt
    ref: /docs/product/pro-chatbot.md — 用户意图分析 & 用户意图响应
    """
    interface_lang = _lang_display_name(profile.language.interface_language)
    target_lang = _lang_display_name(profile.language.target_language)

    prompt = f"""你是 EverLingo 语言学习助手，可以解答用户在 {target_lang} 语言方面的问题。
处理每次用户消息的主要的流程是： 分析当前会话消息和历史消息 -> 识别用户意图 -> [可选:必要时调用提供的 tools] -> 作出友好与实用的回答。

## 术语
先定义下面将使用的术语：
- 语言代码：`en` ： `英语`
- 语言代码：`ja` ： `日本語`
- 语言代码：`zh-CN` ： `简体中文`
- `target_lang`: 用户的`目标学习语言`
- `interface_lang`: 用户的`界面语言`
- `single_word` : {target_lang} 是 `英语` 时为1个单词，是 `简体中文` 时为一个中文词语，是 `日本語` 时为一个日文词语

## 配置
- 界面语言(interface_lang): {interface_lang}
- 目标学习语言(target_lang): {target_lang}

### 用户个性化(User Profile)配置
以下列出已经配置的用户个性化(User Profile)选项：
"""

    # 添加用户背景信息
    if profile.background.hobbies:
        prompt += f"\n- 用户爱好(hobbies): {profile.background.hobbies}"
    if profile.background.residence:
        prompt += f"\n- 居住地区(residence): {profile.background.residence}"
    if profile.background.gender:
        prompt += f"\n- 性别(gender): {profile.background.gender}"
    if profile.dictionary_definition_style:
        prompt += f"\n- 词典解释风格(dictionary_definition_style): {profile.dictionary_definition_style}"

    prompt += f"""

## 用户意图分类

分析判断用户意图，然后作出响应。

用户意图包括：
1. `查单词`
2. `翻译`
3. `查询与修改配置` 

## 用户意图识别

`用户意图类型` 按识别优先级从高到低分为：
1. 查词（Word Lookup）
2. 翻译（Translation）
3. 配置管理
4. 其它语言学习问题
5. 未识别输入


以下说明意图识别的方法。使用 LLM 对意图进行识别。根据 chatbot session 的历史消息上下文，用户的最近消息，识别用户意图。


### 1. 查词（Word Lookup）
**判定条件**：
你从用户消息判断意图是明确地要查询 {target_lang} 语言的一个或多个`single_word`，而不是翻译
OR
标点符号除外,输入是纯 {target_lang} 文本 AND 只有一个 `single_word`

### 2. 翻译（Translation）
**判定条件**：
你从用户消息判断意图是明确地要翻译一段 {target_lang} 语言的文本，而不是查询单词
OR
标点符号除外，输入消息大部分是 {target_lang} 文本，首个出现的单词或词语是 {target_lang} 语言文本，输入由多个 `single_word` 组成

### 3. 配置管理
**判定条件**：
- 用户询问当前设置（如"我的配置是什么"）
- 用户要求修改设置（如"把界面语言改成英语"）

### 4. 其它语言学习问题
**判定条件**：
你从用户消息判断是一个语言学习的问题，但不能匹配到已知的 `用户意图类型` 。但你有信心解答这个问题。

### 4. 未识别输入
**判定条件**：
非语言学习相关的询问


## 用户意图响应

规则：用 {interface_lang} 作为主语言回复用户消息。

### 查词（Word Lookup）响应或 `single_word` 释义的输出要求
查词输出要求最少有以下信息：
- 用 {interface_lang} 语言表达的`single_word`语义说明

个性化增加：
1. 根据 `用户 Profile` 提供个性化的释义。如`hobbies`、`dictionary_definition_style`、`residence`、`gender`。只使用已经配置过的用户个性化属性。

可选增加：
1. 词源故事（用通俗易懂的方式讲述这个单词的来源和演变）
2. 文化背景（给出贴合用户生活的记忆技巧或联想）
3. 使用场景举例（1-2个例句，附带{interface_lang}翻译）

### 翻译输出要求
翻译输出为 `界面语言` 。适当地根据 `用户 Profile` 个性化，如`hobbies`、`residence`、`gender`。 只使用已经配置过的用户个性化属性。

- 标注翻译中值得注意的句式或短语
- 如果有多种译法，列出备选方案并说明差异
- 提供学习建议（如语法点、常见搭配等）


### 配置管理
**响应要求**：
使用 conf_manager 工具集中的函数：
- get_config: 查询当前配置
- set_config: 修改配置
- get_schema: 获取配置说明

### 未识别输入
**响应要求**：
礼貌地提示用户输入不明确，并给出使用示例：
- 查词示例：输入目标语言的单个词
- 翻译示例：输入目标语言的句子
- 配置管理示例：询问或修改配置

## 用户显式模式指定

用户可以通过 `/dict`、`/translate` 等命令在会话中设定模式。
当模式被设定后，用户消息前会附加一条 SystemMessage 提示当前模式，
格式为 `当前模式为「查词/翻译」，用户下一条消息应视为查词/翻译请求`。

**优先级规则**：该 SystemMessage 指定的模式优先级高于自动意图识别。
LLM 应以此模式为准，直接按指定模式处理用户消息，无需再进行意图判断。

"""

    return prompt


class MainAgent:
    """EverLingo 主 Agent。

    产品文档中的"词典老师"、"翻译老师"均由同一个 langchain agent 实现。
    ref: /docs/impl-spec/agents-spec.md
    """

    def __init__(self, profile: UserProfile) -> None:
        self._llm = create_llm()
        self._tools = get_all_tools()
        self._agent = create_agent(
            self._llm,
            tools=self._tools,
            system_prompt=_build_system_prompt(profile),
        )
        # 记录构建时的配置版本，用于检测是否需要重建 agent
        self._config_version = get_config_version()
        # Agent 的消息历史，支持多轮会话
        self._messages: list = []
        # 用户显式意图模式: None=自动, "dict"=查词, "translate"=翻译
        self._intent_mode: Optional[str] = None

    def _refresh_agent_if_needed(self) -> None:
        """检查配置版本，若 set_config 被调用过则重建 agent。

        ref: /docs/impl-spec/agents-spec.md — _build_system_prompt 依赖配置
        """
        current_version = get_config_version()
        if current_version != self._config_version:
            logger.info("system prompt refreshed: {current_version} != {self._config_version}")
            profile = load_profile()
            self._agent = create_agent(
                self._llm,
                tools=self._tools,
                system_prompt=_build_system_prompt(profile),
            )
            self._config_version = current_version

    def _handle_command(self, text: str) -> MessageEvent:
        """处理模式切换命令，直接返回回复（不经过 LLM）。

        ref: /docs/impl-spec/agents-spec.md — 用户显式模式指定
        """
        cmd = text.split()[0].lower()

        if cmd == '/dict':
            self._intent_mode = 'dict'
            return MessageEvent(
                text="已切换到查词模式。以后发送的消息将被视为查词请求。\n"
                     "发送 `/` 可回到自动识别模式。"
            )

        if cmd == '/translate':
            self._intent_mode = 'translate'
            return MessageEvent(
                text="已切换到翻译模式。以后发送的消息将被视为翻译请求。\n"
                     "发送 `/` 可回到自动识别模式。"
            )

        if cmd == '/':
            self._intent_mode = None
            return MessageEvent(text="已回到自动识别模式。")

        if cmd == '/help':
            mode_desc = (
                '自动识别' if self._intent_mode is None
                else ('查词' if self._intent_mode == 'dict' else '翻译')
            )
            return MessageEvent(text=(
                "可用命令：\n"
                "/dict      - 切换到查词模式（后续消息视为查词请求）\n"
                "/translate - 切换到翻译模式（后续消息视为翻译请求）\n"
                "/          - 回到自动识别意图模式\n"
                "/help      - 显示此帮助\n\n"
                f"当前模式：{mode_desc}"
            ))

        return MessageEvent(text=f"未知命令：{cmd}\n发送 /help 查看可用命令。")

    def invoke(self, input_msg: MessageEvent) -> MessageEvent:
        """处理用户消息，返回 Agent 的回复。

        ref: /docs/impl-spec/agents-spec.md — 用户意思的执行与回复响应
        """
        # 若配置被修改过，先重建 agent 以刷新 system prompt
        self._refresh_agent_if_needed()

        text = input_msg.text.strip()

        # ── 模式切换命令（不经过 LLM，不写入历史）────────────
        if text.startswith('/'):
            return self._handle_command(text)

        # ── 构建 LLM 输入消息列表 ─────────────────────────────
        messages_for_llm = list(self._messages)

        # 显式模式下注入 SystemMessage 提示，不污染用户原文
        if self._intent_mode is not None:
            mode_name = "查词" if self._intent_mode == "dict" else "翻译"
            messages_for_llm.append(
                SystemMessage(
                    content=f"当前模式为「{mode_name}」，用户下一条消息应视为{mode_name}请求"
                )
            )

        messages_for_llm.append(HumanMessage(content=text))
        # 将用户消息写入持久化历史（不含模式提示）
        self._messages.append(HumanMessage(content=text))

        # ── 调用 LLM ──────────────────────────────────────────
        try:
            response = self._agent.invoke({"messages": messages_for_llm})
        except Exception as e:
            logger.exception("agent.invoke failed")
            return MessageEvent(text=f"处理请求时出错: {e}")

        # 持久化 AI 回复（跳过 messages_for_llm 中注入的模式提示）
        new_messages = response["messages"][len(messages_for_llm):]
        self._messages.extend(new_messages)

        last_message = self._messages[-1]
        if hasattr(last_message, "content") and last_message.content:
            return MessageEvent(text=last_message.content)
        return MessageEvent(text="抱歉，我无法处理你的请求。")
