"""界面文案（后端用户可见兜底文案）i18n。

ref: docs/i18n/i18n.md — Phase 2 Chat Agent 兜底文案 i18n
边界：仅处理后端直接下发给用户的兜底文案。system prompt 本身不国际化
（给 LLM 看的指令，LLM 依 interface_lang 自行决定回复语言）。
"""
from .messages import FALLBACK_LANG, MESSAGES, t
from .pwa import parse_accept_language, resolve_manifest_language
from .version import VERSION_MESSAGES, version_t

__all__ = [
    "FALLBACK_LANG",
    "MESSAGES",
    "t",
    "parse_accept_language",
    "resolve_manifest_language",
    "VERSION_MESSAGES",
    "version_t",
]
