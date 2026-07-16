from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from everlingo import workspace
from everlingo.wiki.builder import (
    _clean_content_dir,
    _generate_index_md,
    _generate_root_html,
    _write_lang_config,
    wiki_build,
)


def test_clean_content_dir_creates(tmp_path: Path):
    d = tmp_path / "content"
    _clean_content_dir(d)
    assert d.is_dir()


def test_clean_content_dir_empties(tmp_path: Path):
    d = tmp_path / "content"
    d.mkdir()
    (d / "keep_me").mkdir()
    (d / "file.txt").write_text("x")
    (d / "sub" / "nested").mkdir(parents=True)
    (d / "sub" / "nested" / "a.md").write_text("x")
    _clean_content_dir(d)
    assert d.is_dir()
    assert list(d.iterdir()) == []


def test_generate_index_md():
    result = _generate_index_md("en")
    assert "title: English 知识库" in result
    assert "description: English 学习笔记与知识点" in result
    assert "# English 知识库" in result


def test_generate_index_md_unknown_lang():
    result = _generate_index_md("zz")
    assert "title: zz 知识库" in result


def test_generate_root_html_single_lang(tmp_path: Path):
    _generate_root_html(tmp_path, ["en"])
    html = (tmp_path / "index.html").read_text()
    assert '<meta http-equiv="refresh" content="0; url=/en/">' in html
    assert "English 知识库" in html


def test_generate_root_html_multi_lang(tmp_path: Path):
    _generate_root_html(tmp_path, ["en", "ja"])
    html = (tmp_path / "index.html").read_text()
    assert "EverLingo Wiki" in html
    assert '/en/"' in html
    assert '/ja/"' in html
    assert "English" in html
    assert "日本語" in html


def test_write_lang_config(tmp_path: Path):
    overlay = tmp_path / "overlay.yaml"
    overlay.write_text("configuration:\n  baseUrl: localhost\n  ignorePatterns: []\nplugins: []")
    qdir = tmp_path / "quartz"
    qdir.mkdir()
    _write_lang_config(overlay, qdir, "en")
    config = qdir / "quartz.config.yaml"
    assert config.is_file()
    content = config.read_text()
    assert "localhost/en" in content


def test_write_lang_config_with_path_in_baseurl(tmp_path: Path):
    overlay = tmp_path / "overlay.yaml"
    overlay.write_text(
        "configuration:\n  baseUrl: wiki.example.com/wiki\n  ignorePatterns: []\nplugins: []"
    )
    qdir = tmp_path / "quartz"
    qdir.mkdir()
    _write_lang_config(overlay, qdir, "ja")
    content = (qdir / "quartz.config.yaml").read_text()
    assert "wiki.example.com/wiki/ja" in content


def test_wiki_static_files_html_mode(tmp_path: Path):
    from starlette.applications import Starlette
    from starlette.testclient import TestClient

    from everlingo.wiki.builder import WikiStaticFiles

    d = tmp_path / "wiki-dist"
    (d / "en" / "items" / "vocab").mkdir(parents=True)
    (d / "en" / "items" / "vocab" / "ufo.html").write_text("<html>ufo</html>")
    (d / "en" / "items" / "vocab" / "index.html").write_text("<html>vocab index</html>")
    (d / "en" / "index.html").write_text("<html>en index</html>")

    app = Starlette()
    app.mount("/", WikiStaticFiles(directory=str(d), html=True))
    client = TestClient(app)

    resp = client.get("/en/items/vocab/ufo")
    assert resp.status_code == 200
    assert resp.text == "<html>ufo</html>"

    resp = client.get("/en/items/vocab/")
    assert resp.status_code == 200
    assert resp.text == "<html>vocab index</html>"

    resp = client.get("/en/items/vocab/ufo.html")
    assert resp.status_code == 200
    assert resp.text == "<html>ufo</html>"

    resp = client.get("/en/items/vocab/nonexistent")
    assert resp.status_code == 404


def test_wiki_build_no_langs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    monkeypatch.setattr(workspace, "lang_dirs", lambda: [], raising=False)
    # Should not raise, just print "no language vaults"
    wiki_build(workspace_path=tmp_path, dist_dir=tmp_path / "dist")
    assert not (tmp_path / "dist").is_dir()


def test_wiki_build_with_lang_and_mocked_quartz(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)

    vault = tmp_path / "memory" / "languages" / "en" / "vault"
    (vault / "items" / "vocab").mkdir(parents=True)
    (vault / "items" / "vocab" / "foo.md").write_text("---\ntitle: Foo\n---\n# Foo")
    (vault / "events").mkdir()
    (vault / "spec").mkdir()

    monkeypatch.setattr(workspace, "lang_dirs", lambda: ["en"], raising=False)
    monkeypatch.setattr(
        workspace, "lang_vault_dir", lambda lang: vault, raising=False
    )

    quartz_dir = tmp_path / "quartz"
    (quartz_dir / "content").mkdir(parents=True)
    (quartz_dir / "package.json").write_text('{"name":"test"}')
    (quartz_dir / "node_modules" / ".stamp").mkdir(parents=True)

    overlay = tmp_path / "quartz.config.yaml"
    overlay.write_text("configuration:\n  ignorePatterns: []\nplugins: []")

    dist = tmp_path / "dist"

    calls: list[list[str]] = []

    def _fake_run(args, **kwargs):
        calls.append(args)
        # Simulate quartz build: create output dir with index.html
        # Find --output in args
        try:
            o_idx = args.index("--output")
            out_dir = Path(args[o_idx + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "index.html").write_text("<html></html>")
            (out_dir / "static").mkdir(exist_ok=True)
        except (ValueError, IndexError):
            pass
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    wiki_build(
        workspace_path=tmp_path,
        dist_dir=dist,
        quartz_dir=quartz_dir,
        config_overlay=overlay,
    )

    assert (dist / "index.html").is_file()
    assert (dist / "en" / "index.html").is_file()

    # Check --directory argument points to content dir
    build_call = [a for a in calls if "build" in a]
    assert build_call
    d_idx = build_call[0].index("--directory")
    assert build_call[0][d_idx + 1] == str(quartz_dir / "content")

    # Verify per-lang config has baseUrl with lang path
    config_path = quartz_dir / "quartz.config.yaml"
    assert config_path.is_file()
    config_text = config_path.read_text()
    assert "localhost/en" in config_text
