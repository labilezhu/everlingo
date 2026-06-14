from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from .models import UserProfile, TranslationRecord


TRANSLATION_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "你是一位专业的翻译老师。\n"
        "用户界面语言: {interface_language}\n"
        "目标学习语言: {target_language}\n"
        "请将以下{source_lang}文本翻译成{target_lang}。\n"
        "翻译后请：\n"
        "1. 标注翻译中值得注意的句式或短语\n"
        "2. 如果有多种译法，列出备选\n"
        "请用 {interface_language} 回答。",
    ),
    (
        "human",
        "原文: {source_text}",
    ),
])


class TranslationTeacher:
    def __init__(self, llm: ChatOpenAI, profile: UserProfile):
        self._llm = llm
        self._profile = profile

    def translate(self, source_text: str) -> TranslationRecord:
        source_lang = self._profile.target_language
        target_lang = self._profile.interface_language
        messages = TRANSLATION_PROMPT.format_messages(
            source_text=source_text,
            source_lang=self._lang_display_name(source_lang),
            target_lang=self._lang_display_name(target_lang),
            interface_language=self._lang_display_name(self._profile.interface_language),
            target_language=self._lang_display_name(self._profile.target_language),
        )
        result = self._llm.invoke(messages)
        return TranslationRecord(
            source_text=source_text,
            target_text=result.content,
            source_lang=source_lang,
            target_lang=target_lang,
            timestamp=datetime.now(),
        )

    @staticmethod
    def _lang_display_name(code: str) -> str:
        names = {"en": "英语", "zh-CN": "简体中文"}
        return names.get(code, code)
