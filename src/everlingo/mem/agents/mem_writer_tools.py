# ref: docs/impl-spec/memory-writer-agent-spec.md — Agent tools
# ref: docs/impl-spec/search/memory-vault-search-spec.md — Writer 集成
# Memory Writer Agent 的 mem_* 工具沙箱。
# 所有工具强制使用相对于 workspace.memory_dir() 的 path，并在工具层校验
# 解析后路径不能逃出 memory_dir（防 ../），否则 LLM 一次幻觉就会写到 workspace 外。
# 此外，对写操作（create_tmp / write / append / remove）在成功后记录 info 日志，
# 描述写了什么文件、什么内容。

from __future__ import annotations

import fnmatch
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Callable

from langchain_core.tools import tool

from ... import workspace
from ...tools import log_tool_call
from ..vault.frontmatter import normalize_frontmatter_text

logger = logging.getLogger(__name__)


# ── 写后索引钩子（gateway 进程设置） ────────────────────────────────
# ref: docs/impl-spec/search/memory-vault-search-spec.md — Writer 集成
# Writer 写完 .md 后调 SearchClient.index_file(path) fire-and-forget。
# 工具层不直接 import SearchClient（gateway 侧才用）—— 改用回调注入。
# 单元测试可设置 _post_write_hook 为 spy / noop。
_post_write_hook: Callable[[str, str], None] | None = None


def set_post_write_hook(hook: Callable[[str, str], None] | None) -> None:
    """设置写后索引钩子。hook(path, op) -> None；op ∈ {'index','delete'}。"""
    global _post_write_hook
    _post_write_hook = hook


def _fire_post_write(rel: str, op: str) -> None:
    """触发钩子。钩子不存在或抛异常时静默吞掉（fire-and-forget）。"""
    if _post_write_hook is None:
        return
    try:
        _post_write_hook(rel, op)
    except Exception as e:  # noqa: BLE001
        logger.warning("post-write hook failed for %s: %s", rel, e)


# ── ULID 生成 ──────────────────────────────────────────────────────────
# ref: memory-writer-agent-spec.md — mem_gen_id · 类似 01JZABD123 格式的随机 id
# 标准 ULID: 26 字符 Crockford base32 = 48-bit ms 时间戳 + 80-bit 随机数。
# 无外部依赖（pyproject.toml 未引入 python-ulid）。spec 示例 "01JZABD123" 是显示
# 用的截短写法，这里生成完整 26 字符 ULID。

_CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode_base32(num: int, length: int) -> str:
    """把整数编码为指定长度的 Crockford base32 字符串（高位在前）。"""
    chars = []
    for _ in range(length):
        chars.append(_CROCKFORD_ALPHABET[num & 0x1F])
        num >>= 5
    return "".join(reversed(chars))


def _gen_ulid() -> str:
    """生成标准 26 字符 ULID。前 10 字符 = ms 时间戳，后 16 字符 = 随机。"""
    ts_ms = int(time.time() * 1000) & 0xFFFFFFFFFFFF
    rand80 = int.from_bytes(os.urandom(10), "big")
    return _encode_base32(ts_ms, 10) + _encode_base32(rand80, 16)


# ── 路径沙箱 ──────────────────────────────────────────────────────────


class PathSandboxError(ValueError):
    """工具路径逃逸出 memory_dir 时抛出。"""


def _memory_root() -> Path:
    """当前 workspace 的 memory 目录（resolve 后绝对路径）。"""
    return workspace.memory_dir().resolve()


def _resolve_safe(rel_path: str) -> Path:
    """把相对 path 解析为 memory_dir 下的绝对路径，并校验不逃逸。

    ref: memory-writer-agent-spec.md — 工具沙箱
    相对路径解析后必须仍然在 memory_dir 之内；否则抛 PathSandboxError。
    空路径视为 memory_dir 本身（用于 list_directory / search / grep 等
    列目录类的工具）。
    """
    root = _memory_root()
    # 空字符串 / "." → memory_dir 根
    if rel_path is None:
        rel_path = ""
    rel = rel_path.strip()
    if rel in ("", "."):
        return root
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as e:
        raise PathSandboxError(
            f"path escapes memory_dir: {rel_path!r}"
        ) from e
    return candidate


# ── 文件/目录元信息 ──────────────────────────────────────────────────


def _file_info(path: Path) -> dict:
    """构造工具返回的统一文件信息 dict。"""
    st = path.stat()
    return {
        "file_name": path.name,
        "size_bytes": st.st_size,
        "create_time": _format_mtime(st.st_ctime),
        "modify_time": _format_mtime(st.st_mtime),
    }


def _format_mtime(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


# ── 工具实现 ──────────────────────────────────────────────────────────


@tool("mem_create_tmp_file")
@log_tool_call("mem_create_tmp_file")
def mem_create_tmp_file() -> str:
    """在 tmp/ 目录下创建一个新的临时 markdown 文件，返回该文件的相对 path。

    文件名 pattern：tmp_<uuid>.md（uuid4 hex）。文件初始为空字符串。
    后续可结合 mem_write_file 写入内容。
    """
    rel = f"tmp/tmp_{uuid.uuid4().hex}.md"
    abs_path = _resolve_safe(rel)
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text("", encoding="utf-8")
    logger.info("mem_create_tmp_file: created %s", rel)
    return rel


@tool("mem_read_file")
@log_tool_call("mem_read_file")
def mem_read_file(path: str) -> str:
    """读取相对 path 指向的文件，返回文本内容。

    path 为相对于 memory_dir 的相对路径。tmp/ 目录下文件可读。
    """
    abs_path = _resolve_safe(path)
    if not abs_path.is_file():
        return f"error: file not found: {path}"
    return abs_path.read_text(encoding="utf-8")


@tool("mem_write_file")
@log_tool_call("mem_write_file")
def mem_write_file(path: str, content: str) -> str:
    """覆盖写入或新建文件。

    自动创建缺失的父目录。成功后 info 日志记录写了什么文件、什么内容。
    写后通过 set_post_write_hook() 注入的钩子触发 SearchClient.index_file(path)，
    失败/未设置钩子时静默吞掉（fire-and-forget）。

    如果 content 含 YAML frontmatter，会先归一化（tolerant parse + safe_dump），
    保证落盘 frontmatter 永远合法，避免 LLM 偶尔写坏（内嵌引号/冒号）。
    """
    abs_path = _resolve_safe(path)
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    content = normalize_frontmatter_text(content)
    abs_path.write_text(content, encoding="utf-8")
    logger.info("mem_write_file: wrote %s, content=%r", path, content)
    _fire_post_write(path, "index")
    return f"ok: wrote {len(content)} chars to {path}"


@tool("mem_append_file")
@log_tool_call("mem_append_file")
def mem_append_file(path: str, content: str) -> str:
    """追加写入文件末尾；文件不存在则创建。

    自动创建缺失的父目录。成功后 info 日志记录追加的内容。
    写后触发 SearchClient.index_file(path) fire-and-forget。
    """
    abs_path = _resolve_safe(path)
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    with abs_path.open("a", encoding="utf-8") as f:
        f.write(content)
    logger.info("mem_append_file: appended to %s, content=%r", path, content)
    _fire_post_write(path, "index")
    return f"ok: appended {len(content)} chars to {path}"


@tool("mem_remove_file")
@log_tool_call("mem_remove_file")
def mem_remove_file(path: str) -> str:
    """删除文件（仅删除文件，不删除目录）。"""
    abs_path = _resolve_safe(path)
    if not abs_path.is_file():
        return f"error: file not found: {path}"
    abs_path.unlink()
    logger.info("mem_remove_file: removed %s", path)
    _fire_post_write(path, "delete")
    return f"ok: removed {path}"


@tool("mem_list_directory")
@log_tool_call("mem_list_directory")
def mem_list_directory(path: str) -> list[dict]:
    """列出指定目录下的直接子项（不递归）。

    返回 [{file_name, size_bytes, create_time, modify_time}]。
    不存在的路径返回空列表。path 留空表示 memory_dir 根。
    """
    abs_path = _resolve_safe(path or "")
    if not abs_path.is_dir():
        return []
    out: list[dict] = []
    for child in sorted(abs_path.iterdir()):
        if child.is_file():
            out.append(_file_info(child))
        else:
            st = child.stat()
            out.append({
                "file_name": child.name,
                "size_bytes": 0,
                "create_time": _format_mtime(st.st_ctime),
                "modify_time": _format_mtime(st.st_mtime),
            })
    return out


@tool("mem_search_files")
@log_tool_call("mem_search_files")
def mem_search_files(path: str, pattern: str) -> list[dict]:
    """按文件名搜索，目录递归。pattern 与 Linux find -name 类似，支持 '*'。

    返回 [{file_path, is_dir}]。file_path 为相对于输入 path 的相对路径（绝对
    路径在内部处理后转换成相对于调用方传入的 path）。
    """
    base = _resolve_safe(path or "")
    if not base.is_dir():
        return []
    out: list[dict] = []
    for root, dirs, files in os.walk(base):
        root_path = Path(root)
        for name in dirs + files:
            if fnmatch.fnmatch(name, pattern):
                full = root_path / name
                rel = full.relative_to(base).as_posix()
                out.append({
                    "file_path": rel,
                    "is_dir": full.is_dir(),
                })
    return out


@tool("mem_grep")
@log_tool_call("mem_grep")
def mem_grep(path: str, pattern: str) -> list[dict]:
    """按内容正则搜索，目录递归。

    返回 [{file_path, matched_text}]。matched_text 为该文件中第一个匹配的行。
    """
    base = _resolve_safe(path or "")
    if not base.is_dir():
        return []
    try:
        compiled = re.compile(pattern)
    except re.error as e:
        return [{"file_path": "", "matched_text": f"error: invalid regex: {e}"}]
    out: list[dict] = []
    for root, _dirs, files in os.walk(base):
        root_path = Path(root)
        for name in files:
            full = root_path / name
            try:
                text = full.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                if compiled.search(line):
                    rel = full.relative_to(base).as_posix()
                    out.append({"file_path": rel, "matched_text": line})
                    break
    return out


@tool("mem_gen_id")
@log_tool_call("mem_gen_id")
def mem_gen_id() -> str:
    """生成一个 26 字符 ULID 格式的随机 id。

    用于新创建的 kb item markdown 文件名与 frontmatter id 字段，形如
    '01JZABD123ABCDEFGHJKMNPQR'。前 10 字符 = ms 时间戳，后 16 字符 = 随机数。
    """
    return _gen_ulid()


# ── 工具列表 ──────────────────────────────────────────────────────────


def build_mem_writer_tools() -> list:
    """按顺序返回 Memory Writer Agent 的工具列表。"""
    return [
        mem_create_tmp_file,
        mem_read_file,
        mem_write_file,
        mem_append_file,
        mem_remove_file,
        mem_list_directory,
        mem_search_files,
        mem_grep,
        mem_gen_id,
    ]