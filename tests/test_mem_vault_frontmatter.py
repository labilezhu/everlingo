# ref: src/everlingo/mem/vault/frontmatter.py — frontmatter 容错解析 + 归一化
# 核心流程：
#   - split_frontmatter: 拆 raw frontmatter + body
#   - tolerant_parse: 严格 yaml.safe_load 失败时回退逐行 key:value 解析
#   - parse_frontmatter: 组合版
#   - normalize_frontmatter_text: 重序列化保证落盘 frontmatter 永远合法
# 边缘流程：LLM Writer 写出含内嵌引号 / 冒号的近似 YAML（log 报错的 4 种真实 case）

from __future__ import annotations

import yaml

from everlingo.mem.vault.frontmatter import (
    normalize_frontmatter_text,
    parse_frontmatter,
    split_frontmatter,
    tolerant_parse,
)


# ── split_frontmatter ──────────────────────────────────────────────


def test_split_returns_none_when_no_frontmatter():
    raw, body = split_frontmatter("# just a heading\n\nbody text")
    assert raw is None
    assert body.startswith("# just a heading")


def test_split_separates_raw_and_body():
    text = "---\nulid: 01AAA\ngod: true\n---\n\n# body"
    raw, body = split_frontmatter(text)
    assert raw == "ulid: 01AAA\ngod: true"
    assert body == "# body"


# ── tolerant_parse: 严格 YAML OK 时直接走 yaml.safe_load ──────────


def test_strict_yaml_passes_through():
    data = tolerant_parse("ulid: 01AAA\ntype: vocab\nseen_count: 3")
    assert data == {"ulid": "01AAA", "type": "vocab", "seen_count": 3}


def test_strict_yaml_list_field():
    raw = "aliases:\n  - foo\n  - bar\ntags: [a, b]"
    data = tolerant_parse(raw)
    assert data == {"aliases": ["foo", "bar"], "tags": ["a", "b"]}


# ── tolerant_parse: 4 个 log 中的真实 case ────────────────────────


def test_tolerant_title_with_embedded_quotes():
    """`title: "god" 释义` —— 内嵌引号让 YAML 把 "god" 当 quoted scalar 提前结束。"""
    raw = 'ulid: 01KWDV\ntype: vocab\nheadword: god\ntitle: "god" 释义'
    data = tolerant_parse(raw)
    assert data["ulid"] == "01KWDV"
    assert data["title"] == '"god" 释义'


def test_tolerant_intro_with_colon_in_value():
    """`intro_in_target_lang: ... "for" and "since": duration vs point in time`"""
    raw = (
        'ulid: 01KWBS\n'
        'intro_in_target_lang: The difference between "for" and "since": '
        "duration vs point in time"
    )
    data = tolerant_parse(raw)
    assert data["ulid"] == "01KWBS"
    assert data["intro_in_target_lang"] == (
        'The difference between "for" and "since": duration vs point in time'
    )


def test_tolerant_intro_with_colon_before_quotes():
    """`intro_in_target_lang: Subject-verb agreement: "I" takes the base form`"""
    raw = (
        "ulid: 01KWB7\n"
        'intro_in_target_lang: Subject-verb agreement: "I" takes the base form '
        "of the verb"
    )
    data = tolerant_parse(raw)
    assert data["ulid"] == "01KWB7"
    assert data["intro_in_target_lang"] == (
        'Subject-verb agreement: "I" takes the base form of the verb'
    )


def test_tolerant_empty_list_fields():
    raw = "aliases:\ntags: []\nrelated:\nulid: 01AAA"
    data = tolerant_parse(raw)
    assert data == {"aliases": [], "tags": [], "related": [], "ulid": "01AAA"}


def test_tolerant_int_coercion():
    raw = "ulid: 01AAA\nseen_count: 7\nschema_version: 1"
    data = tolerant_parse(raw)
    assert data["seen_count"] == 7
    assert data["schema_version"] == 1


# ── parse_frontmatter: 整 .md 文本入口 ─────────────────────────────


def test_parse_frontmatter_extracts_body():
    text = (
        '---\nulid: 01AAA\ntitle: "x" 释义\n---\n\n# body\n\n## s\n'
    )
    fm, body = parse_frontmatter(text)
    assert fm["ulid"] == "01AAA"
    assert fm["title"] == '"x" 释义'
    assert body.startswith("# body")


def test_parse_frontmatter_no_fm_returns_empty_dict():
    fm, body = parse_frontmatter("# heading\nbody")
    assert fm == {}
    assert body == "# heading\nbody"


# ── normalize_frontmatter_text ─────────────────────────────────────


def test_normalize_passthrough_when_no_frontmatter():
    text = "# no fm\nbody"
    assert normalize_frontmatter_text(text) == text


def test_normalize_produces_valid_yaml_for_malformed_fm():
    text = (
        '---\n'
        'ulid: 01KWDV\n'
        'type: vocab\n'
        'headword: god\n'
        'title: "god" 释义\n'
        'intro_in_target_lang: The difference between "for" and "since": '
        "duration vs point in time\n"
        "tags: []\n"
        "aliases:\n"
        "related:\n"
        "seen_count: 1\n"
        "schema_version: 1\n"
        "---\n\n"
        "# body\n\n## 给我的解释\n\n`god` 是英语名词。"
    )
    out = normalize_frontmatter_text(text)
    # 落盘 frontmatter 必须能严格 yaml.safe_load
    fm_text = out.split("---", 2)[1]
    data = yaml.safe_load(fm_text)
    assert data["ulid"] == "01KWDV"
    assert data["title"] == '"god" 释义'
    assert data["intro_in_target_lang"] == (
        'The difference between "for" and "since": duration vs point in time'
    )
    assert data["seen_count"] == 1
    assert data["schema_version"] == 1
    # body 段字节不变
    assert out.endswith("`god` 是英语名词。")


def test_normalize_preserves_body_unchanged():
    text = (
        "---\nulid: 01AAA\ntitle: 'a:b c'\n---\n\n"
        "# heading\n\n```\ncode: block\n```\n\n## s\n"
    )
    out = normalize_frontmatter_text(text)
    body = out.split("---", 2)[2]
    assert body == "\n\n# heading\n\n```\ncode: block\n```\n\n## s\n"
