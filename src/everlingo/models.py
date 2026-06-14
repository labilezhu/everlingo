from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class UserProfile:
    interface_language: str = ""
    target_language: str = ""

    def is_complete(self) -> bool:
        return bool(self.interface_language) and bool(self.target_language)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.interface_language:
            errors.append("界面语言未设置")
        if not self.target_language:
            errors.append("目标学习语言未设置")
        if self.interface_language and self.target_language and self.interface_language == self.target_language:
            errors.append("界面语言和目标学习语言不能相同")
        return errors


@dataclass
class WordQuery:
    word: str
    scene: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    definition: str = ""
    etymology: str = ""
    cultural_context: str = ""
    interface_language: str = ""


@dataclass
class TranslationRecord:
    source_text: str
    target_text: str = ""
    source_lang: str = ""
    target_lang: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


LANGUAGES: dict[str, str] = {
    "en": "英语",
    "zh-CN": "简体中文",
}
