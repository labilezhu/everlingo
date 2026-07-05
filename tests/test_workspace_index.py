# ref: docs/impl-spec/search/memory-vault-search-spec.md — DB 文件位置
from pathlib import Path

from everlingo import workspace


def test_index_dir_is_under_workspace(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    assert workspace.index_dir() == tmp_path / "memory" / "vault_index"


def test_index_db_path_compat(tmp_path: Path, monkeypatch):
    """index_db_path(lang=None) 回退到旧布局路径。"""
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    assert workspace.index_db_path() == tmp_path / "memory" / "vault_index" / "memory.sqlite"


def test_index_db_path_lang(tmp_path: Path, monkeypatch):
    """index_db_path("en") 返回新布局路径。"""
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    assert workspace.index_db_path("en") == tmp_path / "memory" / "languages" / "en" / "index" / "memory.sqlite"


def test_lang_index_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    assert workspace.lang_index_dir("en") == tmp_path / "memory" / "languages" / "en" / "index"


def test_lang_vault_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    assert workspace.lang_vault_dir("en") == tmp_path / "memory" / "languages" / "en" / "vault"


def test_indexer_socket_path(tmp_path: Path, monkeypatch):
    """indexer.sock 在 workspace 根目录（workspace 级共享）。"""
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    assert workspace.indexer_socket_path() == tmp_path / "indexer.sock"


def test_lang_dirs(tmp_path: Path, monkeypatch):
    """lang_dirs 扫描 memory/languages/*/ 目录。"""
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    # 创建两个语言目录
    (tmp_path / "memory" / "languages" / "en" / "vault").mkdir(parents=True)
    (tmp_path / "memory" / "languages" / "ja" / "vault").mkdir(parents=True)
    # 创建一个没有 vault 的目录（不应被列出）
    (tmp_path / "memory" / "languages" / "xx").mkdir(parents=True)
    langs = workspace.lang_dirs()
    assert langs == ["en", "ja"]
