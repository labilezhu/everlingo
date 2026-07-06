# ref: docs/impl-spec/vault-mcp/valut-mcp-spec.md — MCP 2025-11-25 Server
# ref: docs/impl-spec/vault-mcp/valut-mcp-spec-tools.yaml — 工具定义
# 嵌入式 FastMCP Streamable HTTP server，挂在 indexer 进程内子线程。
# 工具：
#   - session.configure：设定会话默认 lang + interface_language（stream 级）
#   - 9 个 fs 工具（ls/read/write/append/grep/find/stat/mkdir/delete/tree）
#   - search：进程内直调 search.search(conn, ...)
# 所有 fs/search 工具在未 configure 时返回 isError=true + 固定文案；
# state 按 MCP stream/session id 索引，stream 关闭即丢弃（不落盘）。

from __future__ import annotations

import datetime
import fnmatch
import logging
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import uvicorn
from fastmcp import Context, FastMCP

from everlingo import workspace
from everlingo.mem.vault.search.protocol import SearchHit
from everlingo.mem.vault.search.search import search as do_search
from everlingo.mem.vault.search.server import AppState

logger = logging.getLogger(__name__)


# 错误文案固定串（spec 强制）
_SESSION_NOT_CONFIGURED_MSG = "session not configured: call session.configure first"

# Lang 合法性校验缓存：避免每次 session.configure 都 walk filesystem
# 进程级不变量：workspace 启动时确定；运行时新 lang 发现由 LangDiscoveryWatcher 处理，
# 调用方（agent）通常应在写入文件后等待 watcher 触发新 lang 出现，再 configure。
# 故此处 cache 不在 watcher 路径上刷新——保守一点，每次 configure 直接查 lang_dirs()。


# ── 会话状态 ─────────────────────────────────────────────────────────


@dataclass
class SessionState:
    """单 MCP stream/session 的状态。

    lang 必填（configure 校验通过后填入）；
    interface_language 可选（config.configure 暴露但未硬性要求）。
    """

    lang: str | None = None
    interface_language: str | None = None


class SessionRegistry:
    """按 MCP session id 索引的 SessionState 内存 dict。

    线程安全（Lock 保护）。不落盘，stream 关闭即丢弃。
    """

    def __init__(self) -> None:
        self._states: dict[str, SessionState] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str) -> SessionState | None:
        with self._lock:
            return self._states.get(session_id)

    def get_or_create(self, session_id: str) -> SessionState:
        with self._lock:
            st = self._states.get(session_id)
            if st is None:
                st = SessionState()
                self._states[session_id] = st
            return st

    def set(self, session_id: str, state: SessionState) -> None:
        with self._lock:
            self._states[session_id] = state

    def pop(self, session_id: str) -> None:
        with self._lock:
            self._states.pop(session_id, None)


# ── 路径安全 ─────────────────────────────────────────────────────────


class PathEscapeError(ValueError):
    """相对路径逃出 lang vault 根。"""


def resolve_vault_path(lang: str, rel: str) -> Path:
    """把 rel 解析为 lang vault 目录下的绝对路径；逃逸抛 PathEscapeError。

    ref: docs/impl-spec/vault-mcp/valut-mcp-spec.md — fs 工具 path 安全
    """
    vault_root = workspace.lang_vault_dir(lang).resolve()
    if not rel:
        return vault_root
    # 不允许绝对路径：以 rel 拼接；resolve() 后 is_relative_to 校验
    candidate = (vault_root / rel).resolve()
    if not candidate.is_relative_to(vault_root):
        raise PathEscapeError(
            f"path escapes vault root: rel={rel!r} resolved={candidate}"
        )
    return candidate


# ── 工具辅助 ─────────────────────────────────────────────────────────


def _require_session(state: SessionRegistry, ctx: Context) -> SessionState:
    """从 ctx 取 session_id，找/创建 SessionState，校验 lang 已设。"""
    sid = ctx.session_id or ""
    if not sid:
        # fastmcp 必给 session_id；防御性 fallback
        sid = "_default"
    sess = state.get_or_create(sid)
    if sess.lang is None:
        raise ValueError(_SESSION_NOT_CONFIGURED_MSG)
    return sess


# ── FastMCP app ──────────────────────────────────────────────────────


def create_mcp_app(state: AppState) -> FastMCP:
    """注册 12 个工具，挂载到共享的 AppState。

    工具实现约定：
    - 成功：返回 dict（FastMCP 自动包成 content+structuredContent）
    - 失败：raise RuntimeError(msg) → FastMCP 设 isError=true + content[0].text=msg
    """
    registry = SessionRegistry()
    mcp = FastMCP(name="everlingo-vault")

    # ── session.configure ────────────────────────────────────────────

    @mcp.tool(
        name="session.configure",
        title="Configure session defaults",
        description=(
            "Set session-level defaults for subsequent tool calls in this MCP session. "
            "MUST be called before any fs tool (ls/read/write/append/grep/find/stat/"
            "mkdir/delete/tree) and the search tool, otherwise those tools return "
            "error 'session not configured: call session.configure first'. "
            "Re-callable to switch defaults (e.g. switch lang mid-session). "
            "Session state lives for the lifetime of this MCP stream; closing the "
            "stream discards it (no persistence)."
        ),
    )
    async def session_configure(
        lang: str | None = None,
        interface_language: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx is None:
            raise RuntimeError("MCP context unavailable")
        if lang is None:
            raise RuntimeError("lang is required by session.configure")
        # 校验 lang 在 workspace 已存在（spec 「lang 合法性」）
        valid_langs = workspace.lang_dirs()
        if lang not in valid_langs:
            raise RuntimeError(
                f"lang not found in workspace: {lang} (available: {valid_langs})"
            )
        sid = ctx.session_id or "_default"
        sess = registry.get_or_create(sid)
        sess.lang = lang
        if interface_language is not None:
            sess.interface_language = interface_language
        return {
            "ok": True,
            "lang": sess.lang,
            "interface_language": sess.interface_language,
        }

    # ── fs 工具 ─────────────────────────────────────────────────────

    @mcp.tool(
        name="ls",
        title="List directory",
        description=(
            "List files and directories under a vault directory. "
            "Only paths inside the vault are allowed."
        ),
    )
    async def ls_tool(
        path: str = "",
        recursive: bool = False,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx is None:
            raise RuntimeError("MCP context unavailable")
        sess = _require_session(registry, ctx)
        # sess.lang 已通过 _require_session 校验非 None
        assert sess.lang is not None
        try:
            root = resolve_vault_path(sess.lang, path)
        except PathEscapeError as e:
            raise RuntimeError(str(e)) from e
        if not root.exists():
            raise RuntimeError(f"path not found: {path!r}")
        if not root.is_dir():
            raise RuntimeError(f"not a directory: {path!r}")
        entries: list[dict[str, Any]] = []
        if recursive:
            for p in sorted(root.rglob("*")):
                try:
                    rel = p.resolve().relative_to(
                        workspace.lang_vault_dir(sess.lang).resolve()
                    ).as_posix()
                except ValueError:
                    continue
                entries.append(
                    {
                        "name": p.name,
                        "path": rel,
                        "type": "dir" if p.is_dir() else "file",
                        "size_bytes": p.stat().st_size if p.is_file() else None,
                    }
                )
        else:
            for p in sorted(root.iterdir()):
                rel = p.name  # 直接子项，basename 即可
                entries.append(
                    {
                        "name": p.name,
                        "path": rel,
                        "type": "dir" if p.is_dir() else "file",
                        "size_bytes": p.stat().st_size if p.is_file() else None,
                    }
                )
        return {"path": path, "entries": entries}

    @mcp.tool(
        name="read",
        title="Read file",
        description="Read a markdown file from the vault.",
    )
    async def read_tool(path: str, ctx: Context | None = None) -> dict[str, Any]:
        if ctx is None:
            raise RuntimeError("MCP context unavailable")
        sess = _require_session(registry, ctx)
        assert sess.lang is not None
        try:
            abs_path = resolve_vault_path(sess.lang, path)
        except PathEscapeError as e:
            raise RuntimeError(str(e)) from e
        if not abs_path.is_file():
            raise RuntimeError(f"file not found: {path!r}")
        content = abs_path.read_text(encoding="utf-8")
        size = abs_path.stat().st_size
        return {"path": path, "content": content, "size_bytes": size}

    @mcp.tool(
        name="write",
        title="Write file",
        description="Create or overwrite a markdown file.",
    )
    async def write_tool(
        path: str, content: str, ctx: Context | None = None
    ) -> dict[str, Any]:
        if ctx is None:
            raise RuntimeError("MCP context unavailable")
        sess = _require_session(registry, ctx)
        assert sess.lang is not None
        try:
            abs_path = resolve_vault_path(sess.lang, path)
        except PathEscapeError as e:
            raise RuntimeError(str(e)) from e
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        data = content.encode("utf-8")
        abs_path.write_bytes(data)
        return {"ok": True, "path": path, "bytes_written": len(data)}

    @mcp.tool(
        name="append",
        title="Append file",
        description="Append content to the end of an existing markdown file.",
    )
    async def append_tool(
        path: str, content: str, ctx: Context | None = None
    ) -> dict[str, Any]:
        if ctx is None:
            raise RuntimeError("MCP context unavailable")
        sess = _require_session(registry, ctx)
        assert sess.lang is not None
        try:
            abs_path = resolve_vault_path(sess.lang, path)
        except PathEscapeError as e:
            raise RuntimeError(str(e)) from e
        if not abs_path.exists():
            raise RuntimeError(f"file not found: {path!r}")
        data = content.encode("utf-8")
        with abs_path.open("ab") as f:
            f.write(data)
        new_size = abs_path.stat().st_size
        return {
            "ok": True,
            "path": path,
            "bytes_appended": len(data),
            "new_size_bytes": new_size,
        }

    @mcp.tool(
        name="grep",
        title="Search text",
        description="Search file contents.",
    )
    async def grep_tool(
        query: str,
        path: str = "",
        ignore_case: bool = True,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx is None:
            raise RuntimeError("MCP context unavailable")
        sess = _require_session(registry, ctx)
        assert sess.lang is not None
        try:
            root = resolve_vault_path(sess.lang, path)
        except PathEscapeError as e:
            raise RuntimeError(str(e)) from e
        if not root.exists():
            raise RuntimeError(f"path not found: {path!r}")
        if root.is_file():
            files = [root]
        else:
            files = [p for p in root.rglob("*") if p.is_file() and p.suffix == ".md"]
        flags = re.IGNORECASE if ignore_case else 0
        try:
            pat = re.compile(query, flags)
        except re.error as e:
            raise RuntimeError(f"invalid regex: {e}") from e
        matches: list[dict[str, Any]] = []
        vault_root = workspace.lang_vault_dir(sess.lang).resolve()
        for f in files:
            try:
                rel = f.resolve().relative_to(vault_root).as_posix()
            except ValueError:
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for ln, line in enumerate(text.splitlines(), start=1):
                if pat.search(line):
                    matches.append(
                        {"file_path": rel, "matched_text": line, "line_number": ln}
                    )
        return {"query": query, "path": path, "matches": matches}

    @mcp.tool(
        name="find",
        title="Find files",
        description="Find files by filename pattern (glob).",
    )
    async def find_tool(
        pattern: str, path: str = "", ctx: Context | None = None
    ) -> dict[str, Any]:
        if ctx is None:
            raise RuntimeError("MCP context unavailable")
        sess = _require_session(registry, ctx)
        assert sess.lang is not None
        try:
            root = resolve_vault_path(sess.lang, path)
        except PathEscapeError as e:
            raise RuntimeError(str(e)) from e
        if not root.exists():
            raise RuntimeError(f"path not found: {path!r}")
        if root.is_file():
            files = [root]
            dirs = []
        else:
            files = [p for p in root.rglob("*") if p.is_file()]
            dirs = [p for p in root.rglob("*") if p.is_dir()]
        vault_root = workspace.lang_vault_dir(sess.lang).resolve()
        hits: list[dict[str, Any]] = []
        for p in files + dirs:
            try:
                rel = p.resolve().relative_to(vault_root).as_posix()
            except ValueError:
                continue
            if fnmatch.fnmatch(p.name, pattern):
                hits.append({"file_path": rel, "is_dir": p.is_dir()})
        return {"pattern": pattern, "path": path, "files": hits}

    @mcp.tool(
        name="stat",
        title="File metadata",
        description="Return file metadata.",
    )
    async def stat_tool(path: str, ctx: Context | None = None) -> dict[str, Any]:
        if ctx is None:
            raise RuntimeError("MCP context unavailable")
        sess = _require_session(registry, ctx)
        assert sess.lang is not None
        try:
            abs_path = resolve_vault_path(sess.lang, path)
        except PathEscapeError as e:
            raise RuntimeError(str(e)) from e
        if not abs_path.exists():
            return {
                "path": path,
                "exists": False,
                "is_dir": None,
                "size_bytes": None,
                "create_time": None,
                "modify_time": None,
            }
        st = abs_path.stat()

        def _fmt(ts: float) -> str:
            return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

        return {
            "path": path,
            "exists": True,
            "is_dir": abs_path.is_dir(),
            "size_bytes": st.st_size if abs_path.is_file() else None,
            "create_time": _fmt(st.st_ctime),
            "modify_time": _fmt(st.st_mtime),
        }

    @mcp.tool(
        name="mkdir",
        title="Create directory",
        description="Create directory recursively.",
    )
    async def mkdir_tool(path: str, ctx: Context | None = None) -> dict[str, Any]:
        if ctx is None:
            raise RuntimeError("MCP context unavailable")
        sess = _require_session(registry, ctx)
        assert sess.lang is not None
        try:
            abs_path = resolve_vault_path(sess.lang, path)
        except PathEscapeError as e:
            raise RuntimeError(str(e)) from e
        abs_path.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "path": path}

    @mcp.tool(
        name="delete",
        title="Delete file",
        description="Delete a file.",
    )
    async def delete_tool(path: str, ctx: Context | None = None) -> dict[str, Any]:
        if ctx is None:
            raise RuntimeError("MCP context unavailable")
        sess = _require_session(registry, ctx)
        assert sess.lang is not None
        try:
            abs_path = resolve_vault_path(sess.lang, path)
        except PathEscapeError as e:
            raise RuntimeError(str(e)) from e
        if abs_path.is_file():
            abs_path.unlink()
        return {"ok": True, "path": path}

    @mcp.tool(
        name="tree",
        title="Directory tree",
        description="Render a recursive directory tree of the vault.",
    )
    async def tree_tool(
        path: str = "", depth: int = 2, ctx: Context | None = None
    ) -> dict[str, Any]:
        if ctx is None:
            raise RuntimeError("MCP context unavailable")
        sess = _require_session(registry, ctx)
        assert sess.lang is not None
        try:
            root = resolve_vault_path(sess.lang, path)
        except PathEscapeError as e:
            raise RuntimeError(str(e)) from e
        if not root.exists():
            raise RuntimeError(f"path not found: {path!r}")
        if not root.is_dir():
            raise RuntimeError(f"not a directory: {path!r}")
        vault_root = workspace.lang_vault_dir(sess.lang).resolve()

        def _build(p: Path, cur_depth: int) -> list[dict[str, Any]]:
            if cur_depth > depth:
                return []
            out: list[dict[str, Any]] = []
            for child in sorted(p.iterdir()):
                try:
                    rel = child.resolve().relative_to(vault_root).as_posix()
                except ValueError:
                    continue
                entry: dict[str, Any] = {
                    "name": child.name,
                    "path": rel,
                    "type": "dir" if child.is_dir() else "file",
                    "size_bytes": (
                        child.stat().st_size if child.is_file() else None
                    ),
                }
                if child.is_dir():
                    entry["children"] = _build(child, cur_depth + 1)
                out.append(entry)
            return out

        return {"path": path, "depth": depth, "entries": _build(root, 1)}

    # ── search ──────────────────────────────────────────────────────

    @mcp.tool(
        name="search",
        title="hybrid search (full-text + embedding)",
        description=(
            "Search the memory vault. Supports exact (full-text) / semantic "
            "(embedding) / hybrid (mixed) modes; default mode=hybrid. "
            "lang parameter overrides session lang if provided; omit to use session lang."
        ),
    )
    async def search_tool(
        q: str,
        lang: str | None = None,
        kind: str | None = None,
        item_type: str | None = None,
        tags: list[str] | None = None,
        mode: str = "hybrid",
        limit: int = 10,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx is None:
            raise RuntimeError("MCP context unavailable")
        sess = _require_session(registry, ctx)
        assert sess.lang is not None
        effective_lang = lang or sess.lang
        # 走 AppState._get_lang_state（懒开 + 404 处理）
        try:
            ls = state._get_lang_state(effective_lang)
        except Exception as e:
            raise RuntimeError(f"lang not available: {effective_lang}: {e}") from e
        if ls.conn is None:
            raise RuntimeError(f"lang not open: {effective_lang}")
        hits: list[SearchHit] = do_search(
            ls.conn,
            q,
            lang=effective_lang,
            embedder=ls.embedder,
            item_type=item_type,
            tags=tags,
            kind=kind,
            mode=mode,  # type: ignore[arg-type]
            limit=limit,
        )
        # 序列化为 MCP 响应（严格对齐 outputSchema）
        return {
            "hits": [_hit_to_dict(h) for h in hits],
            "count": len(hits),
            "took_ms": 0.0,
        }

    return mcp


def _hit_to_dict(h: SearchHit) -> dict[str, Any]:
    chunk: dict[str, Any] | None
    if h.chunk is None:
        chunk = None
    else:
        chunk = {
            "chunk_id": h.chunk.chunk_id,
            "section_title": h.chunk.section_title,
            "section_kind": h.chunk.section_kind,
            "char_offset": h.chunk.char_offset,
            "text": h.chunk.text,
        }
    return {
        "ulid": h.ulid,
        "kind": h.kind,
        "lang": h.lang,
        "item_type": h.item_type,
        "file_path": h.file_path,
        "title": h.title,
        "score": h.score,
        "source": h.source,
        "chunk": chunk,
        "snippet": h.snippet,
    }


# ── Streamable HTTP 入口 ─────────────────────────────────────────────


def run_mcp_server(state: AppState, host: str, port: int) -> None:
    """前台跑 FastMCP streamable HTTP server（阻塞，子线程调用）。"""
    mcp = create_mcp_app(state)
    # http_app 返回 ASGI app + lifespan（需放在 uvicorn 里）
    app = mcp.http_app(transport="streamable-http")
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
        lifespan="on",
    )


def pick_free_port(host: str = "127.0.0.1") -> int:
    """让 OS 分配空闲端口；返回端口号。socket 立即关闭，端口有可能被后续进程抢占
    （MCP server 启动窗口极小，实践中安全）。"""
    import socket as _socket

    s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    try:
        s.bind((host, 0))
        return s.getsockname()[1]
    finally:
        s.close()
