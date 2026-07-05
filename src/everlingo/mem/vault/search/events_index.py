# ref: docs/impl-spec/search/memory-vault-search-spec.md — events 文件特殊处理
# ref: docs/impl-spec/worksplace/memory-vault-spec.md — events 文件
# ref: src/everlingo/mem/vault/events_spec.md — events 文件格式
#
# events 文件含多个 ## Event 段。FTS 与 chunks 两层粒度解耦：
#   - FTS 层：整文件一行入库，kind='event'，ulid 用合成键 'event:{lang}:{date}'
#   - chunks 层：按 ## Event 拆成多行，每行 section_kind='event'
#
# 文件路径示例：en/events/2026/06/2026-06-26.md

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


# 路径 pattern：{lang}/events/{YYYY}/{MM}/{YYYY-MM-DD}.md
_EVENTS_PATH_RE = re.compile(
    r"^(?P<lang>[a-z]{2}(?:-[A-Za-z0-9]+)?)/events/(?P<year>\d{4})/(?P<month>\d{2})/(?P<date>\d{4}-\d{2}-\d{2})\.md$"
)

# USER.md 固定名
_USER_FILENAME = "USER.md"


@dataclass(frozen=True)
class EventFileMeta:
    lang: str
    date: str  # YYYY-MM-DD
    year: str
    month: str


# 路径 pattern：{lang}/items/{item_type}/{slug}--{ulid}.md
_KB_ITEM_PATH_RE = re.compile(
    r"^(?P<lang>[a-z]{2}(?:-[A-Za-z0-9]+)?)/items/(?P<item_type>[^/]+)/(?P<filename>[^/]+\.md)$"
)


@dataclass(frozen=True)
class KbItemFileMeta:
    lang: str
    item_type: str  # 路径段，仅用于 lang 推导；documents.item_type 仍取 frontmatter type


def parse_kb_item_path(rel_path: str) -> KbItemFileMeta | None:
    """解析 kb item 文件路径，返回 KbItemFileMeta；非 kb item 路径返回 None。

    lang 编码在路径前缀 {lang}/items/... 中，不来自 frontmatter。
    """
    p = rel_path.replace("\\", "/")
    m = _KB_ITEM_PATH_RE.match(p)
    if m is None:
        return None
    return KbItemFileMeta(lang=m.group("lang"), item_type=m.group("item_type"))


def parse_event_path(rel_path: str) -> EventFileMeta | None:
    """解析 events 文件路径，返回 EventFileMeta；非 events 文件返回 None。"""
    p = rel_path.replace("\\", "/")
    m = _EVENTS_PATH_RE.match(p)
    if m is None:
        return None
    return EventFileMeta(
        lang=m.group("lang"),
        date=m.group("date"),
        year=m.group("year"),
        month=m.group("month"),
    )


def is_user_file(rel_path: str) -> bool:
    return rel_path.replace("\\", "/").endswith(_USER_FILENAME)


def make_event_ulid(lang: str, date: str) -> str:
    return f"event:{lang}:{date}"


# ── chunks 切分 ─────────────────────────────────────────────────────


_SECTION_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Section:
    title: str
    kind: str  # 'event' / 'preamble'
    text: str
    char_offset: int  # 在 body 内的字符起点


def split_event_sections(body: str) -> list[Section]:
    """按 ## Event 拆 events 文件 body。

    第一个 ## 之前的内容（preamble）记为 kind='preamble' 一段。
    其余每个 ## Event 段记为 kind='event' 一段，section_title 即 'Event'。
    """
    sections: list[Section] = []
    matches = list(_SECTION_RE.finditer(body))
    if not matches:
        if body.strip():
            sections.append(Section(title=None, kind="preamble", text=body, char_offset=0))
        return sections
    # preamble
    first = matches[0]
    if first.start() > 0:
        pre = body[: first.start()]
        if pre.strip():
            sections.append(Section(title=None, kind="preamble", text=pre, char_offset=0))
    for i, m in enumerate(matches):
        title = m.group("title").strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        text = body[start:end]
        sections.append(
            Section(
                title=title,
                kind="event" if title.lower() == "event" else "section",
                text=text,
                char_offset=start,
            )
        )
    return sections
