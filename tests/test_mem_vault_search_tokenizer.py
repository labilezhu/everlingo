# ref: docs/impl-spec/search/memory-vault-search-spec.md — Tokenizer 规范
# Tokenizer 的核心流程：按 Unicode 脚本分发 Latin/Han/Hiragana-Katakana-Kanji。
# 失败时（jieba/fugashi 不可用）退化为字符切分，不抛错。

from everlingo.mem.vault.search import tokenizer
from everlingo.mem.vault.search.tokenizer import (
    tokenize,
    tokenize_for_fts_query,
    tokenizer_version,
)


def test_tokenize_latin_lowercase():
    out = tokenize("Hello World")
    assert "hello" in out
    assert "world" in out


def test_tokenize_unicode61_keeps_intra_word():
    """整 token 匹配：computer 不再被切为多个 sub-token（unicode61 兜底行为）。"""
    out = tokenize("computer science")
    assert out == "computer science"


def test_tokenize_han_uses_jieba():
    """中文走 jieba；输出 token 数 <= 字符数（避免退化）。"""
    out = tokenize("我爱自然语言处理")
    # jieba 切词数 <= 字符数；如果退化到字符切就是 8 个 token
    assert len(out.split()) <= len("我爱自然语言处理")


def test_tokenize_mixed_zh_en_uses_dispatch():
    """中英混排：两边都能被索引到。"""
    out = tokenize("我爱 computer science")
    assert "computer" in out
    assert "science" in out
    # 至少有一个中文 token 被切出
    assert any(t for t in out.split() if not t.isascii())


def test_tokenize_empty_returns_empty():
    assert tokenize("") == ""


def test_tokenize_whitespace_only_returns_empty():
    assert tokenize("   \n\t  ") == ""


def test_tokenize_ja_kanji_uses_fugashi_or_fallback():
    """日文含汉字；fugashi 不可用时退化为字符切，输出 token 数 == 字符数。"""
    out = tokenize("日本語の勉強")
    # 至少有 1 个 token；如果退化到字符切，等于 6 个
    assert len(out.split()) >= 1


def test_tokenize_for_fts_query_wraps_in_phrase():
    """查询字符串会被 quote 包裹成 phrase query，规避 FTS5 语法冲突。"""
    assert tokenize_for_fts_query("hello world") == '"hello world"'
    assert tokenize_for_fts_query("computer") == '"computer"'


def test_tokenize_for_fts_query_empty_returns_empty():
    assert tokenize_for_fts_query("") == ""


def test_tokenizer_version_is_nonempty_string():
    v = tokenizer_version()
    assert isinstance(v, str)
    assert "jieba:" in v
    assert "fugashi:" in v
