# ref: docs/impl-spec/vault-mcp/vault-mcp-spec.md — VAULT_SPEC.md 与 spec/ 不入索引
# is_excluded_vault_file 统一排除 tmp/ 子目录、spec/ 子目录与 VAULT_SPEC.md。
# walk_vault / sync.reconcile / watcher._dispatch 都通过该 helper 收口。

from __future__ import annotations

from pathlib import Path

from everlingo.mem.vault.search.indexer import is_excluded_vault_file, walk_vault


def _touch(p: Path, content: str = "x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_excludes_tmp_subdirectory(tmp_path: Path) -> None:
    memory_root = tmp_path
    _touch(memory_root / "items" / "vocab" / "a--01JZH0001.md")
    _touch(memory_root / "tmp" / "draft.md")
    paths = [p.name for p in walk_vault(memory_root)]
    assert "a--01JZH0001.md" in paths
    assert "draft.md" not in paths


def test_excludes_vault_spec_md(tmp_path: Path) -> None:
    memory_root = tmp_path
    _touch(memory_root / "items" / "vocab" / "a--01JZH0002.md")
    _touch(memory_root / "VAULT_SPEC.md", "# spec\n")
    paths = [p.name for p in walk_vault(memory_root)]
    assert "a--01JZH0002.md" in paths
    assert "VAULT_SPEC.md" not in paths


def test_excludes_vault_spec_md_in_nested_subdir(tmp_path: Path) -> None:
    """VAULT_SPEC.md 即便出现在 items/ 之类子目录也应被排除（按 basename 排除）。"""
    memory_root = tmp_path
    _touch(memory_root / "items" / "vocab" / "a--01JZH0003.md")
    _touch(memory_root / "items" / "vocab" / "VAULT_SPEC.md", "noise")
    assert is_excluded_vault_file(
        memory_root / "items" / "vocab" / "VAULT_SPEC.md", memory_root
    )
    assert not is_excluded_vault_file(
        memory_root / "items" / "vocab" / "a--01JZH0003.md", memory_root
    )


def test_excludes_spec_subdirectory(tmp_path: Path) -> None:
    """spec/ 子目录（含任意 .md）不应被索引。"""
    memory_root = tmp_path
    _touch(memory_root / "spec" / "vault_spec.md", "# vault spec\n")
    _touch(memory_root / "spec" / "events_spec.md", "# events\n")
    _touch(memory_root / "spec" / "kb_items_spec.md", "# kb items\n")
    _touch(memory_root / "items" / "vocab" / "a--01JZH0004.md")
    paths = [p.name for p in walk_vault(memory_root)]
    assert "a--01JZH0004.md" in paths
    assert "vault_spec.md" not in paths
    assert "events_spec.md" not in paths
    assert "kb_items_spec.md" not in paths


def test_helper_returns_true_for_path_outside_vault(tmp_path: Path) -> None:
    """abs_path 不在 memory_root 下 → 排除（防止 rglob 误捕）。"""
    outside = tmp_path.parent / "somewhere-else.md"
    outside.write_text("x", encoding="utf-8")
    try:
        assert is_excluded_vault_file(outside, tmp_path) is True
    finally:
        outside.unlink()
