# ref: docs/impl-spec/search/memory-vault-search-spec.md — Writer 集成
# 写后钩子：mem_write_file / mem_append_file / mem_remove_file 触发
# set_post_write_hook 注入的回调；gateway 侧通过 SearchClient 投递。
# 单元测试只测钩子被正确调用，不依赖 SearchClient 真实连接。

from __future__ import annotations

from pathlib import Path

import pytest

from everlingo import workspace
from everlingo.mem.agents import mem_writer_tools


@pytest.fixture
def memory_root(tmp_path: Path, monkeypatch):
    root = tmp_path / "memory" / "languages" / "en" / "vault"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    mem_writer_tools.set_current_lang("en")
    return root


def test_mem_write_file_triggers_post_write_hook(memory_root: Path):
    calls: list[tuple[str, str, str]] = []
    mem_writer_tools.set_post_write_hook(lambda lang, p, op: calls.append((lang, p, op)))
    p = "items/vocab/aimai--01JZW1001.md"
    result = mem_writer_tools.mem_write_file.invoke({"path": p, "content": "x"})
    assert "ok" in result
    assert calls == [("en", p, "index")]


def test_mem_append_file_triggers_post_write_hook(memory_root: Path):
    calls: list[tuple[str, str, str]] = []
    mem_writer_tools.set_post_write_hook(lambda lang, p, op: calls.append((lang, p, op)))
    p = "events/2026/06/2026-06-26.md"
    (memory_root / "events" / "2026" / "06").mkdir(parents=True, exist_ok=True)
    (memory_root / p).write_text("# 当天事件\n", encoding="utf-8")
    result = mem_writer_tools.mem_append_file.invoke({"path": p, "content": "## Event\n"})
    assert "ok" in result
    assert calls == [("en", p, "index")]


def test_mem_remove_file_triggers_post_write_hook(memory_root: Path):
    calls: list[tuple[str, str, str]] = []
    mem_writer_tools.set_post_write_hook(lambda lang, p, op: calls.append((lang, p, op)))
    p = "items/vocab/aimai--01JZW1002.md"
    (memory_root / p).parent.mkdir(parents=True, exist_ok=True)
    (memory_root / p).write_text("x", encoding="utf-8")
    result = mem_writer_tools.mem_remove_file.invoke({"path": p})
    assert "ok" in result
    assert calls == [("en", p, "delete")]


def test_no_hook_set_does_not_raise(memory_root: Path):
    mem_writer_tools.set_post_write_hook(None)
    p = "items/vocab/aimai--01JZW1003.md"
    # 不应抛错
    result = mem_writer_tools.mem_write_file.invoke({"path": p, "content": "x"})
    assert "ok" in result


def test_hook_exception_does_not_break_tool(memory_root: Path, caplog):
    def bad_hook(lang, p, op):
        raise RuntimeError("boom")

    mem_writer_tools.set_post_write_hook(bad_hook)
    p = "items/vocab/aimai--01JZW1004.md"
    with caplog.at_level("WARNING"):
        result = mem_writer_tools.mem_write_file.invoke({"path": p, "content": "x"})
    # 写仍然成功（fire-and-forget）
    assert "ok" in result
    # 钩子异常被吞掉
    assert any("post-write hook failed" in m for m in [r.message for r in caplog.records])
