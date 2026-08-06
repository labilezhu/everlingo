# ref: docs/i18n/i18n.md — Phase 2 Chat Agent 兜底文案 i18n
# 后端「用户可见兜底文案」的语言字典与取值函数。
# 边界：仅处理后端直接下发给用户的文案；system prompt（给 LLM 的指令）不在此列。

FALLBACK_LANG = "en"


# {lang: {key: text}}。key 缺失 lang 回退 FALLBACK_LANG；lang 与 key 均缺失回退 key 本身。
# 支持 {placeholder} 占位，由 t() 的 kwargs 通过 .format() 填充。
MESSAGES: dict[str, dict[str, str]] = {
    "zh-CN": {
        "error_retry": "出错了，请稍后重试: {error}",
        "ai_unavailable": "AI 服务暂时不可用，请稍后重试 (已自动重试 2 次)",
        "system_notice_error": "处理系统通知时出错: {error}",
        "error_generic": "出错了，请稍后重试",
    },
    "en": {
        "error_retry": "Something went wrong, please try again later: {error}",
        "ai_unavailable": (
            "AI service is temporarily unavailable, please try again later "
            "(auto-retried 2 times)"
        ),
        "system_notice_error": "Error while processing system notification: {error}",
        "error_generic": "Something went wrong, please try again later",
    },
}


def t(key: str, interface_language: str, **kwargs: str) -> str:
    """按界面语言取文案；缺失 lang 回退 en，缺失 key 回退 key 本身。

    kwargs 用于 {placeholder} 占位填充（.format()）。
    """
    template = MESSAGES.get(interface_language, {}).get(key)
    if template is None:
        template = MESSAGES.get(FALLBACK_LANG, {}).get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            # 占位不匹配时不抛错，原样返回模板
            return template
    return template
