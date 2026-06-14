import re

from .models import UserProfile

CHINESE_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fff]")


class IntentAnalyzer:
    def __init__(self, profile: UserProfile):
        self.profile = profile

    def analyze(self, user_input: str) -> str:
        text = user_input.strip()
        if not text:
            return "unknown"

        if self._is_target_language(text):
            wc = self._word_count(text)
            if self.profile.target_language == "zh-CN":
                if wc <= 4:
                    return "word"
                return "translation"
            if wc <= 1:
                return "word"
            return "translation"

        return "unknown"

    def _is_target_language(self, text: str) -> bool:
        target = self.profile.target_language
        if target == "zh-CN":
            return bool(CHINESE_CHAR_PATTERN.search(text))
        if target == "en":
            return text.isascii() and any(c.isalpha() for c in text)
        return False

    def _word_count(self, text: str) -> int:
        target = self.profile.target_language
        if target == "zh-CN":
            return len(text)
        if target == "en":
            return len(text.split())
