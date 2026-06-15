from datetime import datetime

from langchain_core.messages import AIMessage

from .models import UserProfile, WordQuery


class DictionaryTeacher:
    def __init__(self, agent, profile: UserProfile):
        self._agent = agent
        self._profile = profile

    def lookup(self, word: str, scene: str = "") -> WordQuery:
        input_text = f"单词: {word}\n出现场景: {scene or '未记录'}"
        result = self._agent.invoke(
            {"messages": [{"role": "user", "content": input_text}]}
        )
        last_msg: AIMessage = result["messages"][-1]
        return WordQuery(
            word=word,
            scene=scene,
            timestamp=datetime.now(),
            definition=last_msg.content,
            interface_language=self._profile.interface_language,
        )

    @staticmethod
    def _lang_display_name(code: str) -> str:
        names = {"en": "英语", "zh-CN": "简体中文"}
        return names.get(code, code)
