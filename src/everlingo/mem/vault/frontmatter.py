# ref: docs/impl-spec/search/memory-vault-search-spec.md — frontmatter 解析
# Memory vault 的 .md 文件以 YAML frontmatter 开头（`---\n...\n---\n`）。
# frontmatter 实际由 LLM Writer 手写（mem_writer_agent），LLM 常产出近似 YAML
# 但在含内嵌引号/冒号的值上写坏（如 `title: "god" 释义`、
# `intro_in_target_lang: ...: duration vs point in time`）。
#
# 本模块提供：
#   - split_frontmatter: 拆出 raw frontmatter 文本 + body
#   - tolerant_parse: 严格 yaml.safe_load 失败时回退到逐行 key:value 解析
#   - parse_frontmatter: 组合 split + tolerant_parse，indexer / search 走这里
#   - normalize_frontmatter_text: 用 tolerant_parse 取出字段后用 yaml.safe_dump
#     重序列化，确保落盘 frontmatter 永远合法；供 mem_write_file 在写盘前调用
#
# 设计取舍：
#   - tolerant_parse 只保证「顶层 scalar / 已知 list 字段」能取回；多行复杂结构
#     （如嵌套 mapping）走 yaml.safe_load 仍可能失败，但 vault frontmatter 实际全是
#     平铺的 scalar + 三个 list（aliases/related/tags），覆盖实际使用面。
#   - normalize 用 yaml.safe_dump + sort_keys=False + allow_unicode=True 保留
#     key 顺序与中文字符，不引入外部风格。

from __future__ import annotations

import logging
import re
from typing import Any

import yaml

logger = logging.getLogger(__name__)


_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(?P<fm>.*?)\n---\s*\n?(?P<body>.*)$",
    re.DOTALL,
)


# 已知 list 字段：空值或 `[]` → []，后续缩进 `- ` 续行收集为 list
_LIST_KEYS = frozenset({"aliases", "related", "tags"})

# 已知 int 字段：safe_load 失败时尝试 int() 兜底
_INT_KEYS = frozenset({"seen_count", "schema_version"})

# 顶层 scalar key 行：`key: value` 形式
_KEY_LINE_RE = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?P<value>.*)$")
# list 续行：以空白起头 + `- ` 前缀
_LIST_ITEM_RE = re.compile(r"^\s+-\s+(?P<item>.+?)\s*$")


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """拆出 raw frontmatter 文本与 body。

    Returns:
        (raw_frontmatter, body)：无 frontmatter 时 raw_frontmatter = None。
    """
    m = _FRONTMATTER_RE.match(text)
    if m is None:
        return None, text
    return m.group("fm"), m.group("body")


def tolerant_parse(raw: str) -> dict[str, Any]:
    """解析 frontmatter 原始文本为 dict。

    先尝试 yaml.safe_load；失败时回退到逐行 key:value 解析。
    总是返回 dict（无内容时返回 {}）。
    已知 list 字段被 yaml.safe_load 解析为 None 时（bare `key:` 无值），
    归一化为 []。
    """
    data: dict[str, Any] | None = None
    if raw.strip():
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as e:
            logger.warning("frontmatter YAML 解析失败，回退逐行解析: %s", e)
    if not isinstance(data, dict):
        data = _line_based_parse(raw)
    for k in _LIST_KEYS:
        if k in data and data[k] is None:
            data[k] = []
    return data


def _coerce_scalar(value: str, key: str) -> Any:
    """按字段类型把字符串值转成合适类型。"""
    v = value.strip()
    if key in _INT_KEYS:
        try:
            return int(v)
        except (ValueError, TypeError):
            return v
    if v == "" or v == "[]":
        if key in _LIST_KEYS:
            return []
        return ""
    if key in _LIST_KEYS and v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [s.strip().strip("'\"") for s in inner.split(",") if s.strip()]
    return v


def _line_based_parse(raw: str) -> dict[str, Any]:
    """逐行解析 frontmatter。"""
    out: dict[str, Any] = {}
    current_list_key: str | None = None
    for line in raw.splitlines():
        if not line.strip():
            current_list_key = None
            continue

        if line[:1] in (" ", "\t") and current_list_key is not None:
            m_item = _LIST_ITEM_RE.match(line)
            if m_item:
                if not isinstance(out.get(current_list_key), list):
                    out[current_list_key] = []
                out[current_list_key].append(m_item.group("item").strip())
            continue

        m = _KEY_LINE_RE.match(line)
        if m is None:
            continue
        key = m.group("key")
        value = m.group("value").rstrip()
        coerced = _coerce_scalar(value, key)
        out[key] = coerced
        if isinstance(coerced, list):
            current_list_key = key
        else:
            current_list_key = None
    return out


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """从 .md 文本中拆出 frontmatter dict 与 body（容错）。"""
    raw, body = split_frontmatter(text)
    if raw is None:
        return {}, text
    return tolerant_parse(raw), body


def _dump_frontmatter(data: dict[str, Any]) -> str:
    """把 dict 序列化为合法 YAML block 风格。"""
    return yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=4096,
    )


def normalize_frontmatter_text(text: str) -> str:
    """如果 text 包含 frontmatter，解析后用 yaml.safe_dump 重序列化。

    目的：保证落盘的 kb item 文件 frontmatter 永远合法 YAML，
    避免 LLM Writer 偶尔写坏的字符（内嵌引号/冒号）让 indexer 解析失败。
    body 段字节不变。
    """
    raw, body = split_frontmatter(text)
    if raw is None:
        return text
    data = tolerant_parse(raw)
    if not data:
        return text
    dumped = _dump_frontmatter(data)
    sep = "" if body.startswith("\n") else "\n"
    return f"---\n{dumped}---\n{sep}{body}"
