# ref: docs/impl-spec/search/memory-vault-search-spec.md — events 文件特殊处理
# ref: src/everlingo/mem/vault/events_spec.md — events 文件格式
from pathlib import Path

import pytest

from everlingo.mem.vault.search import events_index
from everlingo.mem.vault.search.events_index import (
    make_event_ulid,
    parse_event_path,
    split_event_sections,
)


def test_parse_event_path_valid():
    meta = parse_event_path("events/2026/06/2026-06-26.md", "en")
    assert meta is not None
    assert meta.lang == "en"
    assert meta.date == "2026-06-26"
    assert meta.year == "2026"
    assert meta.month == "06"


def test_parse_event_path_invalid_returns_none():
    assert parse_event_path("items/vocab/foo--01JZ.md", "en") is None
    assert parse_event_path("events/2026/06/wrong.md", "en") is None
    assert parse_event_path("events/2026/06/2026-06-26.txt", "en") is None



def test_make_event_ulid():
    assert make_event_ulid("ja", "2026-06-26") == "event:ja:2026-06-26"


def test_split_event_sections_basic():
    body = (
        "# 当天事件\n\n"
        "事件按时间顺序记录。\n\n"
        "## Event\n"
        "字段...略\n"
        "### mean_summary\n"
        "summary1\n\n"
        "## Event\n"
        "字段...略\n"
        "### mean_summary\n"
        "summary2\n"
    )
    secs = split_event_sections(body)
    kinds = [s.kind for s in secs]
    titles = [s.title for s in secs]
    assert "preamble" in kinds
    event_secs = [s for s in secs if s.kind == "event"]
    assert len(event_secs) == 2
    assert event_secs[0].title == "Event"
    assert "summary1" in event_secs[0].text


def test_split_event_sections_no_header():
    body = "no header here"
    secs = split_event_sections(body)
    assert len(secs) == 1
    assert secs[0].kind == "preamble"
    assert secs[0].text == "no header here"


def test_split_event_sections_empty():
    assert split_event_sections("") == []
