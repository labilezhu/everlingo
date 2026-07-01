# ref: docs/impl-spec/search/memory-vault-search-spec.md — 索引维护 CLI
# CLI 经 HTTP 委托 indexer；indexer 不在线时 reindex 报错退出。

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from everlingo import workspace
from everlingo.mem.vault.search import cli


def test_indexer_status_when_no_indexer_returns_1(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    args = argparse.Namespace()
    rc = cli.cmd_indexer_status(args)
    assert rc == 1


def test_reindex_when_no_indexer_returns_1(tmp_path: Path, monkeypatch, caplog):
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    args = argparse.Namespace(path=None, rebuild=False, verbose=False)
    with caplog.at_level("ERROR"):
        rc = cli.cmd_reindex(args)
    assert rc == 1


def test_reindex_rebuild_when_no_indexer_returns_1(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    args = argparse.Namespace(path=None, rebuild=True, verbose=False)
    rc = cli.cmd_reindex(args)
    assert rc == 1
