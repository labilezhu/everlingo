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


def test_embed_when_no_indexer_returns_1(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    args = argparse.Namespace(rebuild=False, batch=64, fire_and_forget=False)
    rc = cli.cmd_embed(args)
    assert rc == 1


def test_cli_parser_includes_embed_subcommand():
    """everlingo mem embed 子命令应在 parser 里。"""
    parser = cli.build_parser()
    # 无参数会触发 SystemExit；用 parse_args([]) 看 sub 列表
    import pytest as _pt

    with _pt.raises(SystemExit):
        parser.parse_args([])  # required=True 触发 SystemExit
    # 但 parser 已注册 subparsers
    assert "embed" in parser._subparsers._group_actions[0].choices  # type: ignore[attr-defined]
