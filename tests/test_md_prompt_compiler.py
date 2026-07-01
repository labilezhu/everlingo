"""Tests for the markdown prompt compiler.

see: docs/impl-spec/markdown-prompt-compiler.md
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from everlingo.utils.md_prompt_compiler import (
    CompileError,
    FilesystemSource,
    IncludeCycleError,
    IncludeNotFoundError,
    PackageSource,
    compile_prompt,
    shift_headings,
)


# ---------------- helpers ----------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------- basic expansion ----------------


def test_single_include_with_heading_offset(tmp_path: Path) -> None:
    """Top-level include under a level-2 heading: child h1 -> h3."""
    _write(
        tmp_path / "child.md",
        "# Child Title\n\nchild body\n",
    )
    _write(
        tmp_path / "parent.md",
        "# Parent\n\nintro.\n\n## Section\n\n{{ include [child](child.md) }}\n",
    )
    out = compile_prompt(
        "parent.md", FilesystemSource(base_dir=tmp_path)
    )
    assert "### Child Title" in out
    assert "child body" in out
    assert "## Section" in out
    assert out.count("{{ include") == 0


def test_no_include_returns_unchanged_structure(tmp_path: Path) -> None:
    _write(tmp_path / "a.md", "# A\n\nhello\n")
    out = compile_prompt("a.md", FilesystemSource(base_dir=tmp_path))
    assert "# A" in out
    assert "hello" in out


def test_chained_includes(tmp_path: Path) -> None:
    _write(tmp_path / "leaf.md", "# Leaf\n\nleaf body\n")
    _write(
        tmp_path / "mid.md",
        "## Mid Section\n\n{{ include [leaf](leaf.md) }}\n",
    )
    _write(
        tmp_path / "root.md",
        "# Root\n\nintro\n\n{{ include [mid](mid.md) }}\n\n## After\n\ndone\n",
    )
    out = compile_prompt("root.md", FilesystemSource(base_dir=tmp_path))
    assert "## Mid Section" in out
    # leaf h1 is under mid's h2 (offset=2+1-1=2) -> h3
    assert "### Leaf" in out
    assert "leaf body" in out
    assert "## After" in out


# ---------------- heading-level transformation rules ----------------


def test_heading_offset_promotes_child_higher(tmp_path: Path) -> None:
    """Include at top level (no surrounding heading) → child stays at h1."""
    _write(tmp_path / "kid.md", "# Kid\n\nk\n")
    _write(tmp_path / "p.md", "{{ include [kid](kid.md) }}\n")
    out = compile_prompt("p.md", FilesystemSource(base_dir=tmp_path))
    assert "# Kid" in out
    assert "### Kid" not in out


def test_heading_offset_for_min_level_gt_1(tmp_path: Path) -> None:
    """Child with min level 2 included under a h2 section → h3 / h4."""
    _write(tmp_path / "kid.md", "## Kid\n\nk\n\n### Sub\n\nx\n")
    _write(
        tmp_path / "p.md",
        "## Section\n\nintro\n\n{{ include [kid](kid.md) }}\n",
    )
    out = compile_prompt("p.md", FilesystemSource(base_dir=tmp_path))
    assert "### Kid" in out
    assert "#### Sub" in out


def test_heading_offset_clamped_to_h6(tmp_path: Path) -> None:
    """Heights past h6 must clamp to h6, not crash."""
    _write(
        tmp_path / "tall.md",
        "## Big\n\nbody\n\n### Sub\n\nx\n\n#### Deep\n\ny\n",
    )
    _write(
        tmp_path / "p.md",
        "##### section\n\n{{ include [tall](tall.md) }}\n",
    )
    out = compile_prompt("p.md", FilesystemSource(base_dir=tmp_path))
    assert "###### Big" in out
    assert "###### Sub" in out
    assert "###### Deep" in out
    # no level > 6 marker
    assert "#######" not in out
    assert "########" not in out


def test_heading_offset_top_level_keeps_child_at_h1(tmp_path: Path) -> None:
    """Include at top level (no surrounding heading) → child h1 stays h1 (offset 0)."""
    _write(tmp_path / "kid.md", "# Kid\n\nk\n")
    _write(tmp_path / "p.md", "{{ include [kid](kid.md) }}\n")
    out = compile_prompt("p.md", FilesystemSource(base_dir=tmp_path))
    assert "# Kid" in out
    assert "## Kid" not in out


# ---------------- include directive parsing ----------------


def test_extra_whitespace_in_directive_is_tolerated(tmp_path: Path) -> None:
    _write(tmp_path / "a.md", "# A\n\nax\n")
    _write(
        tmp_path / "p.md",
        "## s\n\n{{   include  [a](a.md)  }}\n",
    )
    out = compile_prompt("p.md", FilesystemSource(base_dir=tmp_path))
    assert "### A" in out
    assert "ax" in out


def test_paragraph_without_directive_is_kept(tmp_path: Path) -> None:
    _write(tmp_path / "a.md", "# A\n\nax\n")
    _write(
        tmp_path / "p.md",
        "## s\n\nnot an include [a](a.md) plain text\n",
    )
    out = compile_prompt("p.md", FilesystemSource(base_dir=tmp_path))
    assert "not an include" in out
    # the link is rendered as a link, and a.md is NOT inlined
    assert "[a](a.md)" in out
    assert "### A" not in out
    assert "ax" not in out


# ---------------- source resolution ----------------


def test_relative_include_in_subdir(tmp_path: Path) -> None:
    _write(tmp_path / "sub" / "leaf.md", "# Leaf\n\nL\n")
    _write(
        tmp_path / "root.md",
        "## S\n\n{{ include [leaf](sub/leaf.md) }}\n",
    )
    out = compile_prompt("root.md", FilesystemSource(base_dir=tmp_path))
    assert "### Leaf" in out
    assert "L" in out


def test_absolute_path_uses_filesystem(tmp_path: Path) -> None:
    absolute = tmp_path / "abs.md"
    _write(absolute, "# Abs\n\nabsolute body\n")
    _write(
        tmp_path / "p.md",
        "## S\n\n{{ include [abs](" + str(absolute) + ") }}\n",
    )
    out = compile_prompt("p.md", FilesystemSource(base_dir=tmp_path))
    assert "### Abs" in out
    assert "absolute body" in out


def test_absolute_path_promotes_outside_package() -> None:
    """An absolute path inside a package source should still hit the filesystem.

    We place the entry inside the real ``everlingo`` package via a small md
    file added at test setup, then include an absolute path outside the
    package.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        abs_md = Path(td) / "abs.md"
        _write(abs_md, "# Abs\n\nA\n")
        # Use a real importable package: put a sibling md file under the
        # package data path so the entry is reachable through PackageSource.
        entry_rel = "_abs_path_promote_entry.md"
        entry_path = (
            Path(__file__).resolve().parent.parent
            / "src"
            / "everlingo"
            / "utils"
            / entry_rel
        )
        try:
            _write(
                entry_path,
                f"## S\n\n{{{{ include [abs]({abs_md}) }}}}\n",
            )
            src = PackageSource(package="everlingo.utils")
            out = compile_prompt(entry_rel, src)
            assert "### Abs" in out
            assert "A" in out
        finally:
            if entry_path.exists():
                entry_path.unlink()


# ---------------- package source ----------------


def test_package_source_resolves_to_real_pkg_file() -> None:
    """Compile the in-tree vault_spec.md via PackageSource."""
    src = PackageSource(package="everlingo.mem.vault")
    out = compile_prompt("vault_spec.md", src)
    # vault_spec includes kb_items_spec and events_spec
    assert "知识点类 memory items" in out
    assert "事件类" in out
    # heading promotion: vault_spec h1 stays h1, child h1 under "## items/" -> h3
    # kb_items_spec starts with "# 知识点类 memory items"
    # include is under "## items/ 知识点类 memory items" (level 2 in vault_spec)
    # so child's "# 知识点类" -> "### 知识点类"
    assert "### 知识点类 memory items" in out
    # events_spec starts with "# 事件类"; under "## events/ 事件类" -> "### 事件类"
    assert "### 事件类" in out
    # the include directive itself is gone
    assert "{{ include" not in out


# ---------------- frontmatter ----------------


def test_frontmatter_is_stripped(tmp_path: Path) -> None:
    fm = (
        "---\n"
        "id: 01JZABD123\n"
        "type: vocab\n"
        "title: 曖昧\n"
        "---\n"
    )
    _write(
        tmp_path / "f.md",
        fm + "# Title\n\nbody\n",
    )
    out = compile_prompt("f.md", FilesystemSource(base_dir=tmp_path))
    assert "id: 01JZABD123" not in out
    assert "type: vocab" not in out
    assert "# Title" in out
    assert "body" in out


# ---------------- error cases ----------------


def test_missing_included_file_raises(tmp_path: Path) -> None:
    _write(
        tmp_path / "p.md",
        "## s\n\n{{ include [nope](missing.md) }}\n",
    )
    with pytest.raises(IncludeNotFoundError):
        compile_prompt("p.md", FilesystemSource(base_dir=tmp_path))


def test_cycle_is_detected(tmp_path: Path) -> None:
    _write(
        tmp_path / "a.md",
        "## s\n\n{{ include [b](b.md) }}\n",
    )
    _write(
        tmp_path / "b.md",
        "## s\n\n{{ include [a](a.md) }}\n",
    )
    with pytest.raises(IncludeCycleError):
        compile_prompt("a.md", FilesystemSource(base_dir=tmp_path))


def test_diamond_include_is_not_a_cycle(tmp_path: Path) -> None:
    """Same file included from two siblings must not raise a cycle error."""
    _write(tmp_path / "shared.md", "# Shared\n\nS\n")
    _write(
        tmp_path / "root.md",
        "# Root\n\n"
        "{{ include [s1](shared.md) }}\n\n"
        "{{ include [s2](shared.md) }}\n",
    )
    out = compile_prompt("root.md", FilesystemSource(base_dir=tmp_path))
    assert out.count("# Shared") == 2
    assert "S" in out


# ---------------- rendering of various blocks ----------------


def test_renders_fenced_code_paragraph_and_list(tmp_path: Path) -> None:
    src = (
        "# T\n\n"
        "intro para with `code` and *em*.\n\n"
        "- one\n- two\n\n"
        "```bash\necho hi\n```\n"
    )
    _write(tmp_path / "m.md", src)
    out = compile_prompt("m.md", FilesystemSource(base_dir=tmp_path))
    assert "# T" in out
    assert "intro para with `code` and *em*." in out
    assert "- one" in out
    assert "- two" in out
    assert "```bash" in out
    assert "echo hi" in out
    assert "```" in out


def test_renders_table(tmp_path: Path) -> None:
    src = (
        "# T\n\n"
        "| a | b |\n"
        "|---|---|\n"
        "| 1 | 2 |\n"
    )
    _write(tmp_path / "m.md", src)
    out = compile_prompt("m.md", FilesystemSource(base_dir=tmp_path))
    assert "| a | b |" in out
    assert "|---|---|" in out
    assert "| 1 | 2 |" in out


def test_renders_blockquote(tmp_path: Path) -> None:
    src = "# T\n\n> quoted line\n"
    _write(tmp_path / "m.md", src)
    out = compile_prompt("m.md", FilesystemSource(base_dir=tmp_path))
    assert "> quoted line" in out


# ---------------- shift_headings ----------------


def test_shift_headings_positive_offset() -> None:
    """Single h1 shifted by +2 becomes h3."""
    md = "# Title\n\nbody\n"
    out = shift_headings(md, 2)
    assert "### Title" in out
    # 行首不应出现 h1（"### Title" 含子串 "# Title"，故用 splitlines 检查）
    for line in out.splitlines():
        assert not line.lstrip().startswith("# Title "), repr(line)
    assert "body" in out


def test_shift_headings_mixed_levels() -> None:
    """h1/h2/h3 each shift by +2 to h3/h4/h5."""
    md = "# A\n\n## B\n\n### C\n"
    out = shift_headings(md, 2)
    assert "### A" in out
    assert "#### B" in out
    assert "##### C" in out


def test_shift_headings_clamp_at_6() -> None:
    """h5 +2 clamps to h6, never exceeds."""
    md = "##### Deep\n\nbody\n"
    out = shift_headings(md, 2)
    assert "###### Deep" in out
    assert "####### Deep" not in out


def test_shift_headings_zero_offset_idempotent() -> None:
    """offset=0 leaves heading levels and content intact."""
    md = "# T\n\npara\n\n## Sub\n\n- a\n- b\n"
    out = shift_headings(md, 0)
    assert "# T" in out
    assert "## Sub" in out
    assert "- a" in out
    assert "- b" in out


def test_shift_headings_preserves_code_fence_hashes() -> None:
    """`#` inside a fenced code block is not a heading and must be unchanged."""
    md = (
        "# Real Heading\n\n"
        "```bash\n"
        "# this is a comment, not a heading\n"
        "echo hi\n"
        "```\n"
    )
    out = shift_headings(md, 2)
    assert "### Real Heading" in out
    assert "# this is a comment, not a heading" in out
    assert "### this is a comment" not in out


def test_shift_headings_negative_offset() -> None:
    """h3 -1 becomes h2; h1 -1 clamps to h1 (no underflow)."""
    md = "### Three\n\n# One\n"
    out = shift_headings(md, -1)
    assert "## Three" in out
    assert "# One" in out
    # ensure no zero-level heading produced
    assert "\n# One\n" in out


def test_shift_headings_no_headings_unchanged() -> None:
    """Pure paragraph text with no headings is rendered unchanged in content."""
    md = "just a paragraph\nwith two lines\n"
    out = shift_headings(md, 2)
    assert "just a paragraph" in out
    assert "with two lines" in out
    assert "#" not in out

