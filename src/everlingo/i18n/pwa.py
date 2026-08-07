# ref: docs/ADR/20260807-pwa-i18n.md — PWA 信息 i18n（Phase 5）
# PWA manifest（name/short_name/description）与 apple-mobile-web-app-title 的语言字典与协商函数。
# 边界：仅 web PWA manifest；不动 Chrome Extension MV3 manifest.json（见 i18n.md Phase 4）。

from __future__ import annotations

from everlingo.models import AVAILABLE_INTERFACE_LANGUAGES, _normalize_lang_tag

FALLBACK_LANG = "en"


# {lang: {key: text}}。lang 缺失回退 FALLBACK_LANG。
# key 集合与 messages.py 一样要求各语言一致（测试保证）。
# name / short_name / description 由 manifest 端点合并进语言无关字段（web/public/manifest.webmanifest）。
PWA_MANIFEST_TEXT: dict[str, dict[str, str]] = {
    "zh-CN": {
        "name": "小记🐹 AI 外语老师",
        "short_name": "小记",
        "description": "小记🐹 AI 外语老师 — 翻译 / 查词 / 聊天，并可视化编辑记忆笔记。",
    },
    "en": {
        "name": "Nori 🐹 AI Language Tutor",
        "short_name": "Nori",
        "description": "Nori 🐹 AI Language Tutor — translate, look up words, chat, and visually edit memory notes.",
    },
}

# 归一化可用语言标签：{"zh-cn": "zh-CN", "en": "en"}
_NORMALIZED_AVAILABLE: dict[str, str] = {
    _normalize_lang_tag(lang): lang for lang in AVAILABLE_INTERFACE_LANGUAGES
}


def _match_lang_tag(tag: str) -> str | None:
    """单个语言标签尝试匹配可用界面语言：精确（归一化后）优先，前缀兜底。

    命中返回规范标签（如 "zh-CN"），未命中返回 None。
    """
    normalized = _normalize_lang_tag(tag)
    if normalized in _NORMALIZED_AVAILABLE:
        return _NORMALIZED_AVAILABLE[normalized]
    if normalized.startswith("zh-") or normalized == "zh":
        return "zh-CN"
    if normalized.startswith("en-") or normalized == "en":
        return "en"
    return None


def parse_accept_language(accept_language: str | None) -> str | None:
    """解析 HTTP `Accept-Language` 头，返回首个命中的可用界面语言；未命中返回 None。

    - 空 / None 头返回 None。
    - 按 q-value 降序解析（缺省 q=1.0；q=0 表示「不接受」，跳过）。
    - 同 q 保持出现顺序；首个命中（精确或前缀）即返回。
    """
    if not accept_language:
        return None

    ranges: list[tuple[float, str]] = []
    for part in accept_language.split(","):
        part = part.strip()
        if not part:
            continue
        pieces = [p.strip() for p in part.split(";")]
        tag = pieces[0]
        q = 1.0
        for p in pieces[1:]:
            if p.lower().startswith("q="):
                try:
                    q = float(p[2:])
                except ValueError:
                    q = 0.0
        if q > 0:
            ranges.append((-q, tag))

    ranges.sort()
    for _, tag in ranges:
        matched = _match_lang_tag(tag)
        if matched:
            return matched
    return None


def resolve_manifest_language(
    accept_language: str | None,
    interface_language: str | None = None,
) -> str:
    """解析 PWA 信息的语言。优先级：

    1. interface_language 非空且 ∈ AVAILABLE_INTERFACE_LANGUAGES → 直接用
       （仅 web_acceptor 传；ws_router 不持有 profile，不传）
    2. parse_accept_language(accept_language) 命中 → 返回
    3. 兜底 "en"

    ref: docs/ADR/20260807-pwa-i18n.md §3.2
    """
    if interface_language and interface_language in AVAILABLE_INTERFACE_LANGUAGES:
        return interface_language
    matched = parse_accept_language(accept_language)
    if matched:
        return matched
    return FALLBACK_LANG


def manifest_text(lang: str, key: str) -> str:
    """按语言取 PWA 文案；lang 缺失回退 en。"""
    text = PWA_MANIFEST_TEXT.get(lang, {}).get(key)
    if text is None:
        text = PWA_MANIFEST_TEXT[FALLBACK_LANG][key]
    return text
