from datetime import datetime

from langchain_core.messages import AIMessage

from .models import UserProfile, TranslationRecord


class TranslationTeacher:
    def __init__(self, agent, profile: UserProfile):
        self._agent = agent
        self._profile = profile

    def translate(self, source_text: str) -> TranslationRecord:
        source_lang = self._profile.target_language
        target_lang = self._profile.interface_language
        result = self._agent.invoke(
            {"messages": [{"role": "user", "content": source_text}]}
        )
        last_msg: AIMessage = result["messages"][-1]
        return TranslationRecord(
            source_text=source_text,
            target_text=last_msg.content,
            source_lang=source_lang,
            target_lang=target_lang,
            timestamp=datetime.now(),
        )

    @staticmethod
    def _lang_display_name(code: str) -> str:
        names = {"en": "英语", "zh-CN": "简体中文"}
        return names.get(code, code)
