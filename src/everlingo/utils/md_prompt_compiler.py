"""markdown prompt compiler.

Resolves ``{{ include [label](path) }}`` directives across markdown files and
returns a single, fully-expanded markdown prompt string. Powered by the
markdown-it-py AST — no regex-based text splicing is used for include
detection or heading-level transformation.

include 指令语法（独占段落）::

    {{ include [label](path) }}

- path 为相对路径 → 引用文件同源
- path 为绝对路径 → filesystem

include 上下文标题层级转换：子文件最浅标题变为 ``context_level + 1``，
子文件所有标题按相同 offset 平移（钳制到 1..6）。

see: docs/impl-spec/markdown-prompt-compiler.md
"""

from __future__ import annotations

import importlib.resources
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

try:
    from importlib.resources.abc import Traversable
except ImportError:  # Python < 3.10
    from importlib.abc import Traversable  # type: ignore[no-redef]

from markdown_it import MarkdownIt
from markdown_it.token import Token


_FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)
_INCLUDE_PREFIX_RE = re.compile(r"\{\{\s*include\s*$")
_INCLUDE_SUFFIX_RE = re.compile(r"^\s*\}\}")


def _strip_frontmatter(text: str) -> str:
    """Strip a leading YAML frontmatter block (---\\n...\\n---\\n) if present."""
    return _FRONTMATTER_RE.sub("", text, count=1)


# ---------------- errors ----------------


class CompileError(Exception):
    """Base error for the prompt compiler."""


class IncludeNotFoundError(CompileError):
    def __init__(self, locator: str) -> None:
        super().__init__(f"included file not found: {locator}")
        self.locator = locator


class IncludeCycleError(CompileError):
    def __init__(self, locator: str) -> None:
        super().__init__(f"include cycle detected at: {locator}")
        self.locator = locator


# ---------------- file sources ----------------


class FileSource(Protocol):
    """A source of markdown files: filesystem or python package.

    A *locator* is an opaque, source-specific string identifying a file:

    - ``FilesystemSource``: an absolute filesystem path.
    - ``PackageSource``: a path relative to the package root
      (e.g. ``"kb_items_spec.md"`` or ``"sub/foo.md"``).
    """

    def read_text(self, locator: str) -> str: ...
    def exists(self, locator: str) -> bool: ...


@dataclass
class FilesystemSource:
    """Markdown files on the local filesystem.

    ``base_dir`` is the directory used to resolve the (relative) entry path.
    Locators produced by this source are absolute filesystem paths.
    """

    base_dir: Path

    def read_text(self, locator: str) -> str:
        return Path(locator).read_text(encoding="utf-8")

    def exists(self, locator: str) -> bool:
        return Path(locator).is_file()


@dataclass
class PackageSource:
    """Markdown files shipped inside a python package.

    Locators are paths relative to the package root.
    """

    package: str

    def _traversable(self, locator: str) -> Traversable:
        return importlib.resources.files(self.package).joinpath(locator)

    def read_text(self, locator: str) -> str:
        return self._traversable(locator).read_text(encoding="utf-8")

    def exists(self, locator: str) -> bool:
        try:
            return self._traversable(locator).is_file()
        except (FileNotFoundError, ModuleNotFoundError, ValueError):
            return False


# ---------------- include directive ----------------


@dataclass(frozen=True)
class IncludeDirective:
    label: str
    target: str  # raw href from the markdown link


# ---------------- public entry ----------------


def compile_prompt(entry_path: str, source: FileSource) -> str:
    """Compile a markdown entry file (and all of its includes) into a prompt.

    Frontmatter is stripped. Include directives are resolved recursively.
    Heading levels of included files are shifted so the included top-level
    heading nests directly under the section that triggered the include.

    ``source`` determines where the entry lives (filesystem or python package).
    Relative includes inherit the source type of the referencing file; absolute
    includes always resolve on the filesystem.
    """
    md = _make_parser()
    fs_for_absolute = FilesystemSource(base_dir=Path("/"))
    entry_locator, entry_source = _resolve_entry(entry_path, source, fs_for_absolute)
    visited: set[str] = set()
    tokens = _compile_file(
        entry_locator, entry_source, visited, context_level=0, md=md
    )
    return _render(tokens)


def shift_headings(md: str, offset: int) -> str:
    """Shift every heading level in ``md`` by ``offset``, clamped to 1..6.

    Complementary to ``compile_prompt``'s internal include-level adjustment:
    that only shifts headings of files pulled in via ``{{ include }}`` and
    leaves the entry file's own headings untouched. ``shift_headings`` operates
    on arbitrary markdown text (typically the output of ``compile_prompt``) and
    shifts *all* headings uniformly.

    Operates on the markdown-it AST, so ``#`` inside fenced code blocks is
    never mistaken for a heading — a limitation of regex-based demotion
    helpers. ``offset`` may be negative; levels are clamped to 1..6.
    """
    md_parser = _make_parser()
    tokens = md_parser.parse(md)
    if offset != 0:
        _apply_heading_offset(tokens, offset)
    return _render(tokens)


def _make_parser() -> MarkdownIt:
    return MarkdownIt("commonmark").enable("table")


def _resolve_entry(
    entry_path: str,
    source: FileSource,
    fs_for_absolute: FilesystemSource,
) -> tuple[str, FileSource]:
    if os.path.isabs(entry_path):
        return entry_path, fs_for_absolute
    if isinstance(source, FilesystemSource):
        locator = (source.base_dir / entry_path).resolve()
        return str(locator), source
    # PackageSource: entry_path is relative to package root
    return entry_path, source


def _resolve_include(
    parent_source: FileSource,
    parent_locator: str,
    rel_path: str,
    fs_for_absolute: FilesystemSource,
) -> tuple[str, FileSource]:
    if os.path.isabs(rel_path):
        return rel_path, fs_for_absolute
    if isinstance(parent_source, FilesystemSource):
        new = (Path(parent_locator).parent / rel_path).resolve()
        return str(new), parent_source
    # PackageSource: relative path stays within the package
    base_dir = os.path.dirname(parent_locator)
    if base_dir:
        combined = os.path.normpath(os.path.join(base_dir, rel_path))
    else:
        combined = os.path.normpath(rel_path)
    if combined == ".." or combined.startswith(".." + os.sep):
        raise CompileError(
            f"include {rel_path!r} from {parent_locator!r} escapes package "
            f"{parent_source.package!r}"
        )
    return combined, parent_source


# ---------------- compile (recursive include expansion) ----------------


def _compile_file(
    locator: str,
    source: FileSource,
    visited: set[str],
    context_level: int,
    md: MarkdownIt,
) -> list[Token]:
    if locator in visited:
        raise IncludeCycleError(locator)
    visited.add(locator)
    try:
        if not source.exists(locator):
            raise IncludeNotFoundError(locator)
        text = source.read_text(locator)
        text = _strip_frontmatter(text)
        tokens = md.parse(text)
        return _expand_includes(
            tokens, source, locator, visited, context_level, md
        )
    finally:
        visited.remove(locator)


def _expand_includes(
    tokens: list[Token],
    source: FileSource,
    parent_locator: str,
    visited: set[str],
    context_level: int,
    md: MarkdownIt,
) -> list[Token]:
    out: list[Token] = []
    current_heading_level = context_level
    i = 0
    n = len(tokens)
    while i < n:
        t = tokens[i]
        if t.type == "heading_open":
            current_heading_level = int(t.tag[1])
        if (
            t.type == "paragraph_open"
            and i + 2 < n
            and tokens[i + 1].type == "inline"
            and tokens[i + 2].type == "paragraph_close"
        ):
            directive = _try_parse_include(tokens[i + 1])
            if directive is not None:
                fs_abs = FilesystemSource(base_dir=Path("/"))
                child_locator, child_source = _resolve_include(
                    source, parent_locator, directive.target, fs_abs
                )
                child_tokens = _compile_file(
                    child_locator, child_source, visited, current_heading_level, md
                )
                child_min = _min_heading_level(child_tokens)
                offset = current_heading_level + 1 - child_min
                if offset != 0:
                    _apply_heading_offset(child_tokens, offset)
                out.extend(child_tokens)
                i += 3
                continue
        out.append(t)
        i += 1
    return out


def _try_parse_include(inline_tok: Token) -> IncludeDirective | None:
    """Parse an include directive from an inline token's children.

    Canonical shape::

        [text("...{{ include"), link_open(href=path),
         text(label), link_close, text("}}...")]

    Arbitrary whitespace is tolerated around the marker.
    """
    children = inline_tok.children
    if not children or len(children) != 5:
        return None
    t1, lo, lt, lc, t2 = children
    if t1.type != "text" or not _INCLUDE_PREFIX_RE.search(t1.content):
        return None
    if lo.type != "link_open":
        return None
    if lt.type != "text":
        return None
    if lc.type != "link_close":
        return None
    if t2.type != "text" or not _INCLUDE_SUFFIX_RE.search(t2.content):
        return None
    href = (lo.attrs or {}).get("href")
    if not href:
        return None
    return IncludeDirective(label=lt.content, target=href)


def _min_heading_level(tokens: list[Token]) -> int:
    """Return the minimum heading level (1..6) in a token list, or 7 if none."""
    m = 7
    for t in tokens:
        if t.type == "heading_open":
            level = int(t.tag[1])
            if level < m:
                m = level
    return m


def _apply_heading_offset(tokens: list[Token], offset: int) -> None:
    """Shift every heading's level by ``offset`` in place, clamping to 1..6."""
    for t in tokens:
        if t.type == "heading_open":
            level = int(t.tag[1])
            new_level = max(1, min(6, level + offset))
            t.tag = f"h{new_level}"


# ---------------- rendering: tokens → markdown ----------------


def _render(tokens: list[Token]) -> str:
    out = _render_block(tokens)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.rstrip() + "\n"


def _render_block(tokens: list[Token]) -> str:
    out: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        t = tokens[i]
        tt = t.type
        if tt == "heading_open":
            level = int(t.tag[1])
            inline = tokens[i + 1]
            out.append("#" * level + " " + _render_inline(inline).strip() + "\n\n")
            i += 3
        elif tt == "paragraph_open":
            inline = tokens[i + 1]
            out.append(_render_inline(inline).rstrip() + "\n\n")
            i += 3
        elif tt == "fence":
            info = (t.info or "").strip()
            out.append("```" + info + "\n" + t.content)
            if not t.content.endswith("\n"):
                out.append("\n")
            out.append("```\n\n")
            i += 1
        elif tt == "code_block":
            out.append("```\n" + t.content)
            if not t.content.endswith("\n"):
                out.append("\n")
            out.append("```\n\n")
            i += 1
        elif tt == "bullet_list_open":
            inner, consumed = _consume(tokens, i, "bullet_list")
            out.append(_render_list(inner))
            i += consumed
        elif tt == "ordered_list_open":
            inner, consumed = _consume(tokens, i, "ordered_list")
            out.append(_render_list(inner))
            i += consumed
        elif tt == "blockquote_open":
            inner, consumed = _consume(tokens, i, "blockquote")
            out.append(_quote_block(_render_block(inner[1:-1])))
            i += consumed
        elif tt == "table_open":
            inner, consumed = _consume(tokens, i, "table")
            out.append(_render_table(inner))
            i += consumed
        elif tt == "hr":
            out.append("---\n\n")
            i += 1
        elif tt == "html_block":
            out.append(t.content.rstrip("\n") + "\n\n")
            i += 1
        else:
            i += 1
    return "".join(out)


def _consume(
    tokens: list[Token], start: int, name: str
) -> tuple[list[Token], int]:
    open_type = name + "_open"
    close_type = name + "_close"
    depth = 0
    i = start
    while i < len(tokens):
        if tokens[i].type == open_type:
            depth += 1
        elif tokens[i].type == close_type:
            depth -= 1
            if depth == 0:
                return tokens[start : i + 1], i + 1 - start
        i += 1
    return tokens[start:], len(tokens) - start


def _quote_block(inner_md: str) -> str:
    lines = inner_md.rstrip("\n").split("\n")
    quoted = "\n".join("> " + line if line else ">" for line in lines)
    return quoted + "\n\n"


def _render_list(list_tokens: list[Token]) -> str:
    out: list[str] = []
    is_ordered = list_tokens[0].type == "ordered_list_open"
    item_num = 1
    if is_ordered and list_tokens[0].attrs:
        s = list_tokens[0].attrs.get("start", 1)
        try:
            item_num = int(s)
        except (TypeError, ValueError):
            item_num = 1
    i = 1
    n = len(list_tokens) - 1
    while i < n:
        t = list_tokens[i]
        if t.type == "list_item_open":
            inner, consumed = _consume(list_tokens, i, "list_item")
            item_body = _render_list_item_body(inner[1:-1])
            marker = f"{item_num}." if is_ordered else "-"
            if is_ordered:
                item_num += 1
            lines = item_body.split("\n")
            first = lines[0] if lines else ""
            rest = lines[1:]
            indent = " " * (len(marker) + 2)
            out.append(f"{marker} {first}")
            out.extend((indent + line) if line else "" for line in rest)
            i += consumed
        else:
            i += 1
    return "\n".join(out) + "\n\n"


def _render_list_item_body(item_tokens: list[Token]) -> str:
    leading = ""
    rest_start = 0
    n = len(item_tokens)
    if n >= 3 and item_tokens[0].type == "paragraph_open":
        leading = _render_paragraph(item_tokens[0:3]).rstrip("\n")
        rest_start = 3
    rest = _render_block(item_tokens[rest_start:]).rstrip("\n")
    if rest:
        rest_lines = rest.split("\n")
        rest = "\n".join(("  " + line) if line else "" for line in rest_lines)
        return leading + "\n" + rest
    return leading


def _render_paragraph(para_tokens: list[Token]) -> str:
    inline = para_tokens[1]
    return _render_inline(inline).rstrip() + "\n\n"


def _render_table(table_tokens: list[Token]) -> str:
    headers: list[str] = []
    rows: list[list[str]] = []
    in_thead = False
    current_row: list[str] | None = None
    current_cell: list[str] | None = None
    i = 1
    n = len(table_tokens) - 1
    while i < n:
        t = table_tokens[i]
        tt = t.type
        if tt == "thead_open":
            in_thead = True
        elif tt == "thead_close":
            in_thead = False
        elif tt == "tr_open":
            current_row = []
        elif tt == "tr_close":
            if current_row is not None:
                if in_thead:
                    headers = current_row
                else:
                    rows.append(current_row)
            current_row = None
        elif tt in ("th_open", "td_open"):
            current_cell = []
        elif tt in ("th_close", "td_close"):
            if current_row is not None and current_cell is not None:
                current_row.append("".join(current_cell).strip())
            current_cell = None
        elif tt == "inline":
            if current_cell is not None:
                current_cell.append(_render_inline(t))
        i += 1
    if not headers:
        return ""
    ncols = len(headers)
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * ncols) + "|"]
    for row in rows:
        padded = list(row) + [""] * (ncols - len(row))
        out.append("| " + " | ".join(padded[:ncols]) + " |")
    return "\n".join(out) + "\n\n"


def _render_inline(tok: Token) -> str:
    children = tok.children
    if not children:
        return tok.content
    out: list[str] = []
    link_href = ""
    for c in children:
        ct = c.type
        if ct == "text":
            out.append(c.content)
        elif ct == "code_inline":
            out.append("`" + c.content + "`")
        elif ct == "softbreak":
            out.append("\n")
        elif ct == "hardbreak":
            out.append("  \n")
        elif ct == "em_open":
            out.append("*")
        elif ct == "em_close":
            out.append("*")
        elif ct == "strong_open":
            out.append("**")
        elif ct == "strong_close":
            out.append("**")
        elif ct == "link_open":
            link_href = (c.attrs or {}).get("href", "")
            out.append("[")
        elif ct == "link_close":
            out.append(f"]({link_href})")
        elif ct == "image":
            src = (c.attrs or {}).get("src", "")
            alt = c.content or ""
            out.append(f"![{alt}]({src})")
        elif ct == "html_inline":
            out.append(c.content)
        else:
            out.append(c.content or "")
    return "".join(out)
