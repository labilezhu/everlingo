from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import yaml
from starlette.staticfiles import StaticFiles

from .. import workspace

_LANG_NAMES: dict[str, str] = {
    "en": "English",
    "ja": "日本語",
    "zh": "中文",
    "fr": "Français",
    "de": "Deutsch",
    "es": "Español",
    "ko": "한국어",
    "ar": "العربية",
    "ru": "Русский",
    "pt": "Português",
    "it": "Italiano",
    "th": "ไทย",
    "vi": "Tiếng Việt",
    "id": "Bahasa Indonesia",
    "hi": "हिन्दी",
}

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DEFAULT_QUARTZ_DIR = _REPO_ROOT / "tools" / "wiki" / "quartz"
_DEFAULT_CONFIG_OVERLAY = _REPO_ROOT / "tools" / "wiki" / "quartz.config.yaml"
_DEFAULT_DIST_DIR = ".wiki-dist"


def _clean_content_dir(content_dir: Path) -> None:
    """Remove everything inside content dir (keep dir itself)."""
    if not content_dir.is_dir():
        content_dir.mkdir(parents=True)
        return
    for item in content_dir.iterdir():
        if item.is_symlink() or item.is_file():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(str(item))


def _generate_index_md(lang: str) -> str:
    name = _LANG_NAMES.get(lang, lang)
    return f"""---
title: {name} 知识库
description: {name} 学习笔记与知识点
---

# {name} 知识库
"""


def _write_lang_config(overlay: Path, quartz_dir: Path, lang: str) -> Path:
    with open(overlay) as f:
        cfg = yaml.safe_load(f)
    base_url = cfg.get("configuration", {}).get("baseUrl", "localhost") or "localhost"
    base_url = base_url.rstrip("/")
    cfg["configuration"]["baseUrl"] = f"{base_url}/{lang}"
    target = quartz_dir / "quartz.config.yaml"
    with open(target, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)
    return target


def _ensure_quartz_plugins(quartz_dir: Path) -> None:
    node_modules = quartz_dir / "node_modules"
    if not node_modules.is_dir():
        print("Running npm install...")
        subprocess.run(
            ["npm", "install"],
            check=True,
            cwd=str(quartz_dir),
        )

    plugins_dir = quartz_dir / ".quartz" / "plugins"
    if plugins_dir.is_dir():
        return
    print("Installing Quartz community plugins (first build)...")
    subprocess.run(
        ["npx", "quartz", "plugin", "install", "--from-config"],
        check=True,
        cwd=str(quartz_dir),
    )


def _build_one_lang(
    quartz_dir: Path,
    vault_dir: Path,
    dist_lang_dir: Path,
    overlay: Path,
    lang: str,
) -> None:
    content_dir = quartz_dir / "content"
    _clean_content_dir(content_dir)

    for subdir in ["items", "events", "spec"]:
        src = vault_dir / subdir
        if src.is_dir():
            (content_dir / subdir).symlink_to(src, target_is_directory=True)

    (content_dir / "index.md").write_text(_generate_index_md(lang))

    _write_lang_config(overlay, quartz_dir, lang)

    dist_lang_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "npx",
            "quartz",
            "build",
            "--directory",
            str(content_dir),
            "--output",
            str(dist_lang_dir),
        ],
        check=True,
        cwd=str(quartz_dir),
    )

    _clean_content_dir(content_dir)


def _generate_root_html(dist_dir: Path, langs: list[str]) -> None:
    index = dist_dir / "index.html"

    if len(langs) == 1:
        lang = langs[0]
        name = _LANG_NAMES.get(lang, lang)
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="0; url=/{lang}/">
<title>{name} 知识库</title>
</head>
<body>
<p><a href="/{lang}/">{name} 知识库</a></p>
</body>
</html>"""
    else:
        cards = "\n".join(
            f'    <a href="/{lang}/" class="lang-card">'
            f'<div class="lang-name">{_LANG_NAMES.get(lang, lang)}</div>'
            f"<div class=\"lang-desc\">{_LANG_NAMES.get(lang, lang)} 知识库</div></a>"
            for lang in langs
        )
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EverLingo Wiki</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: #faf8f8; color: #2b2b2b;
  display: flex; justify-content: center; align-items: center; min-height: 100vh;
}}
.container {{ text-align: center; }}
h1 {{ font-size: 2rem; margin-bottom: 0.5rem; }}
p {{ color: #4e4e4e; margin-bottom: 2rem; }}
.lang-list {{ display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap; }}
.lang-card {{
  display: block; padding: 1.5rem 2.5rem;
  background: white; border: 1px solid #e5e5e5; border-radius: 8px;
  text-decoration: none; color: #2b2b2b; font-size: 1.25rem;
  transition: box-shadow 0.15s, border-color 0.15s;
}}
.lang-card:hover {{ border-color: #284b63; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
.lang-card .lang-name {{ font-weight: 600; }}
.lang-card .lang-desc {{ font-size: 0.85rem; color: #4e4e4e; margin-top: 0.25rem; }}
</style>
</head>
<body>
<div class="container">
  <h1>EverLingo Wiki</h1>
  <p>选择语言知识库</p>
  <div class="lang-list">
{cards}
  </div>
</div>
</body>
</html>"""

    index.write_text(html)
    print(f"  → {index}")


def wiki_build(
    workspace_path: Path | None = None,
    dist_dir: Path | None = None,
    quartz_dir: Path | None = None,
    config_overlay: Path | None = None,
) -> None:
    ws = workspace_path or workspace.current_workspace()
    dist = dist_dir or (ws / _DEFAULT_DIST_DIR)
    qdir = quartz_dir or _DEFAULT_QUARTZ_DIR
    overlay = config_overlay or _DEFAULT_CONFIG_OVERLAY

    langs = workspace.lang_dirs()
    if not langs:
        print("Wiki: no language vaults found, nothing to build.")
        return

    if not overlay.is_file():
        raise FileNotFoundError(
            f"Quartz config overlay not found: {overlay}\n"
            "Make sure tools/wiki/quartz.config.yaml exists."
        )

    _ensure_quartz_plugins(qdir)

    for lang in langs:
        vault = workspace.lang_vault_dir(lang)
        if not vault.is_dir():
            print(f"Wiki: skipping {lang} — vault directory missing at {vault}")
            continue

        print(f"Building wiki for {lang}...")
        _build_one_lang(qdir, vault, dist / lang, overlay, lang)
        print(f"  → {dist / lang}")

    _generate_root_html(dist, langs)
    print(f"Wiki build complete → {dist}")


class WikiStaticFiles(StaticFiles):
    """StaticFiles subclass that appends .html for extensionless paths.

    Starlette's StaticFiles(html=True) does NOT automatically append .html
    to paths without extensions — it only serves index.html for directories
    and falls back to 404.html.  This subclass adds the .html fallback so
    that /en/items/vocab/ufo resolves to en/items/vocab/ufo.html.
    """

    def lookup_path(self, path: str) -> tuple[str, os.stat_result | None]:
        full_path, stat_result = super().lookup_path(path)
        if stat_result is not None:
            return full_path, stat_result
        if self.html and "." not in os.path.basename(path):
            return super().lookup_path(path + ".html")
        return "", None


def wiki_serve(dist_dir: Path, port: int = 8765) -> None:
    if not dist_dir.is_dir() or not (dist_dir / "index.html").is_file():
        raise FileNotFoundError(
            f"Wiki dist directory not ready: {dist_dir}\n"
            "Run 'everlingo wiki build' first."
        )

    import uvicorn

    from starlette.applications import Starlette

    app = Starlette()
    app.mount("/", WikiStaticFiles(directory=str(dist_dir), html=True))
    print(f"Serving wiki at http://localhost:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
