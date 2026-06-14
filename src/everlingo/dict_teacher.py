from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from .models import UserProfile, WordQuery


LOOKUP_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "你是一位专业的词典老师。请用 {interface_language} 解释以下单词。\n"
        "用户的目标学习语言是 {target_language}。\n"
        "请提供：\n"
        "1. 单词释义（用 {interface_language} 解释，兼顾用户可能的母语文化背景）\n"
        "2. 词源故事（用通俗易懂的方式讲述这个单词的来源和演变）\n"
        "3. 文化背景（结合中文用户的文化背景，给出贴合生活的记忆技巧或联想）\n"
        "4. 使用场景举例（1-2 个例句，带 {interface_language} 翻译）\n"
        "如果用户提供了单词出现的场景，请结合场景来讲解。",
    ),
    (
        "human",
        "单词: {word}\n"
        "出现场景: {scene}",
    ),
])


class DictionaryTeacher:
    def __init__(self, llm: ChatOpenAI, profile: UserProfile):
        self._llm = llm
        self._profile = profile

    def lookup(self, word: str, scene: str = "") -> WordQuery:
        messages = LOOKUP_PROMPT.format_messages(
            word=word,
            scene=scene or "未记录",
            interface_language=self._lang_display_name(self._profile.interface_language),
            target_language=self._lang_display_name(self._profile.target_language),
        )
        result = self._llm.invoke(messages)
        return WordQuery(
            word=word,
            scene=scene,
            timestamp=datetime.now(),
            definition=result.content,
            interface_language=self._profile.interface_language,
        )

    @staticmethod
    def _lang_display_name(code: str) -> str:
        names = {"en": "英语", "zh-CN": "简体中文"}
        return names.get(code, code)
