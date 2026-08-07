# ref: docs/i18n/i18n.md — Vault 内容 i18n（Phase 6 补记）
# vault 中由「代码直接写入」的用户可见内容语言字典（LLM 生成内容不在此列，
# 由 LLM 依据 prompt 中的 interface_lang 自行决定，见 i18n.md Phase 6 边界）。
# 当前仅 events 文件首次创建时写入的「文件前置内容」。

from __future__ import annotations

FALLBACK_LANG = "en"


# {lang: text}。lang 缺失回退 FALLBACK_LANG。
# ref: events_spec.md — 当日 events 文件首次创建时写入的「文件前置内容」。
EVENT_FILE_PREAMBLE: dict[str, str] = {
    "zh-CN": (
        "# 当天事件\n\n"
        "事件按时间顺序记录，即最早的事件在前面。\n"
        "事件记录格式：\n\n"
    ),
    "en": (
        "# Today's Events\n\n"
        "Events are recorded in chronological order, earliest first.\n"
        "Event format:\n\n"
    ),
}


def event_file_preamble(interface_language: str) -> str:
    """按界面语言取 events 文件前置内容；lang 缺失回退 en。"""
    return EVENT_FILE_PREAMBLE.get(interface_language, EVENT_FILE_PREAMBLE[FALLBACK_LANG])
