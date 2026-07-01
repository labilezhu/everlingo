# ref: docs/impl-spec/search/memory-vault-search-spec.md — DB 文件位置
from pathlib import Path

from everlingo import workspace


def test_index_dir_is_under_workspace(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    assert workspace.index_dir() == tmp_path / "index"


def test_index_db_path(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    assert workspace.index_db_path() == tmp_path / "index" / "memory.sqlite"


def test_indexer_socket_path(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    assert workspace.indexer_socket_path() == tmp_path / "index" / "indexer.sock"
