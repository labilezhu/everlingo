# ref: agents-spec.md — Agent 实现
# 主要实现在 MainAgent。产品文档中的"词典老师"、"翻译老师"均由同一个 langchain agent 实现。
# ref: /docs/impl-spec/agents-spec.md

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from ..llm import create_agent, create_llm
from ..models import LANGUAGES, UserProfile
from ..setting import load_profile, load_user_doc, prompt_input_mtime
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


def _build_system_prompt(profile: UserProfile, user_doc: str = "") -> str:
    """构建统一的 Agent system prompt，整合词典老师和翻译老师的功能。

    ref: /docs/impl-spec/agents-spec.md — _build_system_prompt
    ref: /docs/product/pro-chatbot.md — 用户意图分析 & 用户意图响应
    """
    interface_lang = _lang_display_name(profile.language.interface_language)
    target_lang = _lang_display_name(profile.language.target_language)

    prompt = f"""你是 EverLingo 语言学习助手，可以解答用户在 {target_lang} 语言方面的问题。
处理每次用户消息的主要的流程是： 分析当前会话消息和历史消息 -> 识别用户意图(当最近系统消息未指定`对话模式`时) -> [可选:必要时调用提供的 tools] -> 作出友好与实用的回答。

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
- `single_word` : {target_lang} 是 `英语` 时为1个单词，是 `简体中文` 时为一个中文词语，其它语言也如此类推。
- `user_message_lang`： 你从用户最近的一条消息去识别出消息主要使用的语言
- `src_lang`： 要查词或翻译的原语言，一般同 `user_message_lang`
- `dest_lang`： 要查词或翻译输出的目标语言。一般默认是 {interface_lang}。 但如果 {interface_lang} 与 `src_lang` 相同时，应为  {target_lang}。 无论如何，`dest_lang` 不能与 `src_lang` 相同。

## 配置
- 界面语言(interface_lang): {interface_lang}
- 目标学习语言(target_lang): {target_lang}

## 用户个性化(User Profile)配置
用户个性化(User Profile)选项：
- 用户语言设置见上方 `配置` 节
"""

    # 用户自由偏好笔记 (USER.md)。由用户以自由文本维护，可由 Agent 通过 user_doc 工具更新。
    # ref: DOMAIN.md — 用户自由偏好笔记 (USER.md)
    if user_doc.strip():
        prompt += f"""
## 用户自由偏好笔记 (USER.md)
以下为用户以自由文本记录的个性化偏好，请在查词/翻译/答疑时予以考虑。
仅使用其中与当前任务相关的部分，不要机械复述。

---
{user_doc.strip()}
---
"""

    prompt += f"""

## 用户意图分类

分析判断用户意图，然后作出响应。

用户意图包括：
1. `智能问答`
2. `查单词`
3. `翻译`
4. `查询与修改配置` 

## 用户显式 `对话模式` 指定

用户可以通过 `/dict`、`/translate` 等命令在会话中设定 `对话模式`。
命令列表和`对话模式`：
- /dict -> `dict` 
- /translate -> `translate` 
- / -> 无模式，自由对话
- /help -> 命令帮助

当`对话模式`被设定后，用户消息前会附加一条 SystemMessage 提示当前模式，
格式为: 当前 `对话模式` 为 [dict/translate]。

**优先级规则**：该 SystemMessage 指定的模式优先级高于自动意图识别。
LLM 应以此模式为准，直接按指定模式处理用户消息，无需再进行意图判断。

`对话模式`到`用户意图` 的映射匹配关系如下：
- `dict` -> `查单词`
- `translate` -> `翻译`

## 用户意图识别

### Case 1: 系统消息指定了 `对话模式`
如最近系统消息指定了 `对话模式`，务必严格按它匹配到 `用户意图`。

### Case 2: 没有系统消息指定 `对话模式`
`用户意图类型` 按识别优先级从高到低分为：
1. 查词（Word Lookup）
2. 翻译（Translation）
3. 配置管理
4. 其它语言学习问题
5. 未识别输入

以下说明意图识别的方法。使用 LLM 对意图进行识别。根据 chatbot session 的历史消息上下文，用户的最近消息，识别用户意图。

#### 1. 查词（Word Lookup）
**判定条件**：
而消息本身在 `user_message_lang` 语言里，是一个 `single_word`

#### 2. 翻译（Translation）
**判定条件**：
你从用户消息判断意图是明确地要翻译文本，而不是查询单词
OR
`user_message_lang` 识别为 {target_lang} 语言文本，且输入由多个 `single_word` 组成

#### 3. 配置管理
**判定条件**：
- 用户询问当前设置（如"我的配置是什么"）
- 用户要求修改设置（如"把界面语言改成英语"）

#### 4. 其它语言学习问题
**判定条件**：
你从用户消息判断是一个语言学习的问题，但不能匹配到已知的 `用户意图类型` 。但你有信心解答这个问题。

#### 5. 未识别输入
**判定条件**：
非语言学习相关的询问


## 用户意图响应

规则：用 {interface_lang} 作为主语言回复用户消息， `dest_lang` 与 {interface_lang} 为不同语言时除外。

### 查词（Word Lookup）响应或 `single_word` 释义的输出要求
查词输出要求最少有以下信息：
- 用 `dest_lang` 语言表达的`single_word`语义说明

个性化增加：
1. 根据 `用户自由偏好笔记 (USER.md)` 提供个性化的释义。只使用其中与该词相关的偏好内容。

如果当前 `对话模式` 为 `dict` 。请不要输出查词释义外的其它前置或后置的用户提示、追问内容，如：
- 当前处于 xyz 模式
- 有什么其他单词想查的吗？

### 翻译输出要求
翻译输出使用 `dest_lang` 语言 。适当地根据 `用户自由偏好笔记 (USER.md)` 个性化。只使用其中与本次翻译相关的偏好内容。

- 标注翻译中值得注意的句式或短语
- 如果有多种译法，列出备选方案并说明差异
- 提供学习建议（如语法点、常见搭配等）

如果当前 `对话模式` 为 `translate` 。请不要输出翻译文本外的其它前置或后置的用户提示、追问内容，如：
- 当前处于 xyz 模式
- 有什么其他需要翻译的吗？

### 配置管理
**响应要求**：
使用 conf_manager 工具集中的函数：
- get_config: 查询当前配置
- set_config: 修改配置
- get_schema: 获取配置说明

用户自由偏好笔记 (USER.md) 的管理使用 user_doc 工具集：
- user_doc_get: 读取当前 USER.md 全文
- user_doc_set: 整体覆盖写入 USER.md。使用流程：先 user_doc_get 读取当前内容 → 在其基础上修改 → user_doc_set 写回完整内容。不要只写入片段。

用户表达个性化偏好（如职业、爱好、性别、地区、年龄、学习目标、释义偏好、翻译偏好等自由文本描述）时，应使用 user_doc 工具更新 USER.md，而非 set_config。

### 未识别输入
**响应要求**：
礼貌地提示用户输入不明确，并给出使用示例：
- 查词示例：输入目标语言的单个词
- 翻译示例：输入目标语言的句子
- `对话模式` 的命令
- 配置管理示例：询问或修改配置

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
        user_doc = load_user_doc()
        self._agent = create_agent(
            self._llm,
            tools=self._tools,
            system_prompt=_build_system_prompt(profile, user_doc),
        )
        # 记录构建时的配置版本与文件 mtime，用于检测是否需要重建 agent
        # ref: agents-spec.md — system prompt 维护
        self._config_version = get_config_version()
        self._prompt_mtime = prompt_input_mtime()
        # Agent 的消息历史，支持多轮会话
        self._messages: list = []
        # 用户显式意图模式: None=自动, "dict"=查词, "translate"=翻译
        self._intent_mode: Optional[str] = None

    def _refresh_agent_if_needed(self) -> None:
        """检查配置版本或依赖文件 mtime，若变化则重建 agent 以刷新 system prompt。

        触发条件（任一即可）：
        - prompt 版本号变化（set_config / user_doc_set 被调用过）
        - everlingo.yaml 或 USER.md 的 mtime 变化（外部编辑器修改）

        ref: /docs/impl-spec/agents-spec.md — _build_system_prompt 依赖配置
        """
        current_version = get_config_version()
        current_mtime = prompt_input_mtime()
        if current_version == self._config_version and current_mtime == self._prompt_mtime:
            return

        logger.info(
            "system prompt refreshed: version %s->%s, mtime %s->%s",
            self._config_version, current_version,
            self._prompt_mtime, current_mtime,
        )
        profile = load_profile()
        user_doc = load_user_doc()
        self._agent = create_agent(
            self._llm,
            tools=self._tools,
            system_prompt=_build_system_prompt(profile, user_doc),
        )
        self._config_version = current_version
        self._prompt_mtime = current_mtime

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
            messages_for_llm.append(
                SystemMessage(
                    content=f"当前 `对话模式` 为 `{self._intent_mode}`"
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
