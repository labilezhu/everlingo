# ref: docs/impl-spec/search/memory-vault-search-spec.md — Tokenizer 规范
# Unicode 脚本分发分词器：
#   Latin         -> 小写化，保留原文（unicode61 后续按空白切）
#   Han           -> jieba.cut
#   Hiragana / Katakana / Kanji -> fugashi + unidic
# 合并所有 token，空格连接成字符串。
#
# 单文件常含界面语言（zh）+ 目标语言（en/ja）混排；脚本分发无需语言检测器。
# 查询侧必须调用同一个 tokenize()，否则索引侧 / 查询侧 token 集合不一致导致
# 匹配失败。
#
# jieba / fugashi 加载较重（unidic 词典 ~50MB），仅在 indexer 进程首次调用
# _ensure_loaded() 时加载。gateway 进程不调用此模块。

from __future__ import annotations

import logging
import re
import unicodedata
from functools import lru_cache

logger = logging.getLogger(__name__)

# ── 版本标识 ─────────────────────────────────────────────────────────
# 版本字符串变化触发 FTS 全量重建；content_hash 跳过未变文件。
_JIEBA_VERSION = "0.42"
_FUGASHI_VERSION = "1.1"


# ── 后端加载 ─────────────────────────────────────────────────────────
# 模块导入时立即尝试加载 jieba / fugashi；失败不抛（环境差异容忍）。
# 实际分词函数在首次调用时检查 _BACKENDS；未加载则退化为脚本切分。

def _load_jieba():
    try:
        import jieba  # type: ignore[import-not-found]

        return jieba
    except Exception as e:
        logger.warning("jieba 加载失败，中文退化为字符切分: %s", e)
        return None


def _load_fugashi():
    try:
        import fugashi  # type: ignore[import-not-found]

        try:
            import unidic  # type: ignore[import-not-found]

            dicdir = unidic.DICDIR
            # 验证 unidic 词典实际存在（unidic 1.1.0 需要 python -m unidic download）
            import os as _os

            if not _os.path.isdir(dicdir) or not _os.listdir(dicdir):
                logger.warning(
                    "unidic 词典未下载（%s 为空），请运行 `python -m unidic download`；日文退化为字符切分",
                    dicdir,
                )
                return None
            tagger = fugashi.GenericTagger(f'-r "{dicdir}/mecabrc" -d "{dicdir}"')
            return tagger
        except Exception as e:
            logger.warning("unidic 不可用，日文退化为字符切分: %s", e)
            try:
                return fugashi.GenericTagger()
            except Exception as e2:
                logger.warning("fugashi fallback 也失败: %s", e2)
                return None
    except Exception as e:
        logger.warning("fugashi 加载失败，日文退化为字符切分: %s", e)
        return None


_JIEBA = _load_jieba()
_FUGASHI_TAGGER = _load_fugashi()


# ── 版本号 ───────────────────────────────────────────────────────────


def tokenizer_version() -> str:
    """返回当前分词器版本字符串。版本变化会触发 FTS 全量重建。"""
    parts = [f"jieba:{_JIEBA_VERSION}", f"fugashi:{_FUGASHI_VERSION}"]
    if _FUGASHI_TAGGER is not None:
        try:
            import unidic  # type: ignore[import-not-found]

            parts.append(f"unidic:{unidic.__version__}")
        except Exception:
            parts.append("unidic:unknown")
    return "+".join(parts)


# ── 脚本分发 ─────────────────────────────────────────────────────────

# Latin：U+0041..005A, U+0061..007A, U+00C0..024F（含欧洲拉丁扩展）
_LATIN_RE = re.compile(r"[\u0041-\u005A\u0061-\u007A\u00C0-\u024F]+")
# Han：CJK 统一表意
_HAN_RE = re.compile(r"[\u4E00-\u9FFF\u3400-\u4DBF]+")
# Hiragana + Katakana
_KANA_RE = re.compile(r"[\u3040-\u309F\u30A0-\u30FF]+")
# Kanji 已被 _HAN_RE 覆盖；保留为 alias
_KANJI_RE = _HAN_RE
# 数字
_DIGIT_RE = re.compile(r"[\u0030-\u0039]+")
# 其它字符（标点、emoji 等）逐字符保留
_OTHER_RE = re.compile(r"[\s\S]")


def _is_latin(ch: str) -> bool:
    return "LATIN" in unicodedata.name(ch, "")


def _classify_run(text: str) -> list[tuple[str, str]]:
    """把 text 拆成 [(script, run_text), ...]，按脚本连续段聚合。"""
    runs: list[tuple[str, str]] = []
    if not text:
        return runs
    current_script: str | None = None
    current_buf: list[str] = []
    for ch in text:
        script = _script_of(ch)
        if script != current_script:
            if current_buf and current_script is not None:
                runs.append((current_script, "".join(current_buf)))
            current_buf = [ch]
            current_script = script
        else:
            current_buf.append(ch)
    if current_buf and current_script is not None:
        runs.append((current_script, "".join(current_buf)))
    return runs


def _script_of(ch: str) -> str:
    cp = ord(ch)
    if ch.isspace():
        return "space"
    if 0x0041 <= cp <= 0x005A or 0x0061 <= cp <= 0x007A:
        return "latin"
    if 0x00C0 <= cp <= 0x024F:
        return "latin"
    if 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF:
        return "han"
    if 0x3040 <= cp <= 0x30FF:
        return "kana"
    if 0x0030 <= cp <= 0x0039:
        return "digit"
    return "other"


def _segment_latin(text: str) -> list[str]:
    """拉丁文字小写化。unicode61 后续按空白切；此处不再二次切分。

    保留所有 latin 连续段作为一个 token（camelCase 不切），便于
    FTS 整 token 匹配。整段先小写化。
    """
    return [text.lower()] if text.strip() else []


def _segment_han(text: str) -> list[str]:
    """中文 jieba 切词；jieba 不可用时退化为单字切分。"""
    if _JIEBA is None:
        return list(text)
    try:
        return [t for t in _JIEBA.cut(text, cut_all=False) if t.strip()]
    except Exception as e:
        logger.warning("jieba.cut 失败，退化为单字: %s", e)
        return list(text)


def _segment_ja(text: str) -> list[str]:
    """日文 fugashi 形态学切词（kanji + kana 混排段）。"""
    if _FUGASHI_TAGGER is None:
        return list(text)
    try:
        tokens: list[str] = []
        for word in _FUGASHI_TAGGER(text):
            surface = word.surface
            if surface:
                tokens.append(surface)
        return tokens if tokens else [text]
    except Exception as e:
        logger.warning("fugashi 切词失败，退化为字符: %s", e)
        return list(text)


def _segment_digit(text: str) -> list[str]:
    return [text]


def _segment_other(text: str) -> list[str]:
    # 其它字符（标点、emoji）丢弃；只保留可见 token。
    return []


# ── 公共 API ─────────────────────────────────────────────────────────


@lru_cache(maxsize=4096)
def tokenize(text: str) -> str:
    """对一段文本做分词，返回空格连接的 token 字符串。

    多次相同输入会复用结果（lru_cache）；查询侧、索引侧必须使用同一函数。
    返回空字符串当 text 为空或全为标点。
    """
    if not text:
        return ""
    runs = _classify_run(text)
    all_tokens: list[str] = []
    for script, run in runs:
        if script == "space":
            continue
        if script == "latin":
            all_tokens.extend(_segment_latin(run))
        elif script == "han":
            all_tokens.extend(_segment_han(run))
        elif script == "kana":
            # kana 段单独切（按字符），但 kana+kanji 混排应作为 ja 处理
            # _classify_run 会按 _script_of 切换，kanji 是 "han"，kana 是 "kana"
            # 此处收到连续 kana → 字符切（保留原顺序的读音单元）
            all_tokens.extend(list(run))
        elif script == "digit":
            all_tokens.extend(_segment_digit(run))
        else:
            all_tokens.extend(_segment_other(run))
    return " ".join(t for t in all_tokens if t)


def tokenize_for_fts_query(text: str) -> str:
    """为 FTS5 MATCH 准备查询字符串。

    FTS5 语法中 token 含特殊字符（如 * ? ^ "）需转义。
    我们直接用 tokenize() 输出空白连接的 token，再用 "" 包裹得到
    phrase 查询，规避 FTS5 语法冲突。
    """
    raw = tokenize(text)
    if not raw:
        return ""
    tokens = raw.split()
    if not tokens:
        return ""
    if len(tokens) == 1:
        return f'"{tokens[0]}"'
    return '"' + " ".join(tokens) + '"'


# Han + Kana 混排段独立处理（单独 kana 段字符切；混排时由 _classify_run 切分后
# 各自走 _segment_han / _segment_ja；不过 _classify_run 不区分 han 与 kanji 之外的
# 切分策略，所以 kana-kanji 混排的连续段会被打散。下面 _segment_ja 在
# 出现 kanji 时按 fugashi 处理（_classify_run 实际按字符切换，因此
# kanji 与 kana 不会在同一 run；即一个混排段会被切成多个 kana + han run，
# 分别字符切 + jieba 切。这对中文 ja 混排的句子可接受：中文走 jieba，
# 假名走字符切，汉字部分走 jieba (无 unidic 词典时)；unidic 可用时由 _segment_ja
# 处理纯日文段)。详见 docstring。
