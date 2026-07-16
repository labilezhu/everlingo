# ref: docs/impl-spec/search/memory-vault-search-spec.md — server.py
# 用 FastAPI TestClient 直接驱动 ASGI app，不真正起 uvicorn / unix socket。
# 覆盖 5 个端点：POST /{lang}/search, POST /{lang}/index, POST /{lang}/delete,
# POST /{lang}/rebuild, GET /status, POST /{lang}/embed

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from everlingo import workspace
from everlingo.mem.vault.search.indexer import count_chunks, count_docs
from everlingo.mem.vault.search.server import AppState, create_app


@pytest.fixture
def memory_root(tmp_path: Path, monkeypatch) -> Path:
    """设置 workspace 到 tmp_path，返回 lang vault 目录。"""
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    root = tmp_path / "memory" / "languages" / "en" / "vault"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def state(tmp_path: Path, memory_root: Path) -> AppState:
    socket_path = tmp_path / "indexer.sock"
    return AppState(socket_path=socket_path, langs=["en"])


@pytest.fixture
def app(state: AppState):
    return create_app(state)


@pytest.fixture
def client(app, state):
    # TestClient 触发 lifespan（state.open / state.close）
    with TestClient(app) as c:
        yield c


def _write_item(memory_root: Path, name: str, ulid: str, body: str = "x", slug: str | None = None) -> Path:
    """写 kb item 文件。新布局：不含 {lang}/ 前缀。文件名即 {slug}.md。"""
    p = memory_root / "items" / "vocab" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    if slug is None:
        slug = Path(name).stem
    p.write_text(f"---\nulid: {ulid}\nslug: {slug}\ntype: vocab\ntitle: aimai\n---\n\n{body}", encoding="utf-8")
    return p


def test_status_after_open(client, state):
    r = client.get("/status")
    assert r.status_code == 200
    data = r.json()
    assert data["running"] is True
    assert "langs" in data
    assert len(data["langs"]) == 1
    lang_info = data["langs"][0]
    assert lang_info["lang"] == "en"
    assert lang_info["docs"] == 0
    assert lang_info["chunks"] == 0
    assert "embedded_chunks" in lang_info
    assert "embedding_model_id" in lang_info


def test_index_then_search(client, state, memory_root: Path):
    _write_item(memory_root, "aimai.md", "01JZD0001", body="あいまい means ambiguous in Japanese")
    rel = "items/vocab/aimai.md"
    r = client.post("/en/index", json={"path": rel})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert count_docs(state._lang_states["en"].conn) == 1

    r = client.post("/en/search", json={"q": "ambiguous", "limit": 10})
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 1
    assert any(h["ulid"] == "01JZD0001" for h in data["hits"])


def test_delete(client, state, memory_root: Path):
    _write_item(memory_root, "x.md", "01JZD0002")
    client.post("/en/index", json={"path": "items/vocab/x.md"})
    assert count_docs(state._lang_states["en"].conn) == 1
    r = client.post("/en/delete", json={"path": "items/vocab/x.md"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert count_docs(state._lang_states["en"].conn) == 0


def test_rebuild(client, state, memory_root: Path):
    _write_item(memory_root, "y.md", "01JZD0003")
    client.post("/en/index", json={"path": "items/vocab/y.md"})
    r = client.post("/en/rebuild")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["indexed"] == 1
    assert count_chunks(state._lang_states["en"].conn) >= 1


def test_index_missing_file_returns_404(client, state):
    r = client.post("/en/index", json={"path": "items/vocab/nonexistent.md"})
    assert r.status_code == 404


def test_embed_endpoint_returns_valid_response(client, state):
    """/en/embed 端点存在且返回结构合法。env 配了 model 时 ok=True，否则 False。"""
    r = client.post("/en/embed", json={})
    assert r.status_code == 200
    data = r.json()
    assert "ok" in data
    assert "total_chunks" in data
    assert "embedded_chunks" in data
    assert "embedding_model_id" in data
    assert "embedding_dim" in data
    assert "took_ms" in data


def test_search_unknown_lang_returns_404(client, state):
    r = client.post("/xx/search", json={"q": "hello"})
    assert r.status_code == 404


# ── 运行时新 lang 发现（lazy open + 顶层 watcher） ─────────────────


def _empty_state(tmp_path: Path) -> "AppState":
    """构造一个启动时无 lang 的 AppState（langs=[]）。"""
    socket_path = tmp_path / "indexer.sock"
    return AppState(socket_path=socket_path, langs=[])


def test_lazy_open_lang_when_dir_appears_after_startup(tmp_path: Path, monkeypatch):
    """indexer 启动后 `en/vault/` 出现，再调 `/{lang}/index` 应能懒加载并索引。"""
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    state = _empty_state(tmp_path)
    app = create_app(state)
    with TestClient(app) as c:
        # 启动时无 lang：/status 应返回空 langs
        r = c.get("/status")
        assert r.status_code == 200
        assert r.json()["langs"] == []

        # 启动后创建 en/vault/ 目录 + 一个 kb item 文件
        en_vault = tmp_path / "memory" / "languages" / "en" / "vault"
        en_vault.mkdir(parents=True)
        p = en_vault / "items" / "vocab" / "god.md"
        p.parent.mkdir(parents=True)
        p.write_text(
            "---\nulid: 01JZDLAZY\nslug: god\ntype: vocab\ntitle: god\n---\n\ndeity supreme being",
            encoding="utf-8",
        )

        # 调用 /en/index 应触发懒加载并成功索引
        r = c.post("/en/index", json={"path": "items/vocab/god.md"})
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
        assert "en" in state._lang_states
        assert count_docs(state._lang_states["en"].conn) == 1

        # /en/search 应能命中
        r = c.post("/en/search", json={"q": "deity", "limit": 10})
        assert r.status_code == 200
        hits = r.json()["hits"]
        assert any(h["ulid"] == "01JZDLAZY" for h in hits)

        # /status 应包含 en
        r = c.get("/status")
        assert any(ls["lang"] == "en" for ls in r.json()["langs"])


def test_lazy_open_missing_vault_returns_404(tmp_path: Path, monkeypatch):
    """lang 根目录存在但 vault 子目录未建 → 端点仍 404。"""
    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    state = _empty_state(tmp_path)
    app = create_app(state)
    with TestClient(app) as c:
        # 只建 en/，不建 en/vault/
        (tmp_path / "memory" / "languages" / "en").mkdir(parents=True)

        r = c.post("/en/index", json={"path": "items/vocab/god2.md"})
        assert r.status_code == 404
        assert "lang not found" in r.json()["detail"]


def test_discovery_watcher_opens_new_lang(tmp_path: Path, monkeypatch):
    """顶层 LangDiscoveryWatcher 应在新 `*/vault/` 出现时自动开 lang 并 reconcile。"""
    import time as _time

    monkeypatch.setattr(workspace, "_current_ws_dir", tmp_path, raising=False)
    monkeypatch.setattr(workspace, "_current_ws_name", None, raising=False)
    state = _empty_state(tmp_path)
    app = create_app(state)
    with TestClient(app) as c:
        # 启动时无 lang
        r = c.get("/status")
        assert r.json()["langs"] == []

        # 模拟外部进程：先 mkdir ja/vault/，再落盘一个 kb item
        ja_vault = tmp_path / "memory" / "languages" / "ja" / "vault"
        ja_vault.mkdir(parents=True)
        p = ja_vault / "items" / "vocab" / "aimai.md"
        p.parent.mkdir(parents=True)
        p.write_text(
            "---\nulid: 01JZDLAZJ\nslug: aimai\ntype: vocab\ntitle: aimai\n---\n\nあいまい ambiguous",
            encoding="utf-8",
        )

        # 等 watchdog 事件触发 + reconcile；轮询 /status
        deadline = _time.monotonic() + 5.0
        ok = False
        while _time.monotonic() < deadline:
            r = c.get("/status")
            if any(ls["lang"] == "ja" for ls in r.json()["langs"]):
                if "ja" in state._lang_states:
                    if count_docs(state._lang_states["ja"].conn) >= 1:
                        ok = True
                        break
            _time.sleep(0.1)
        assert ok, "discovery watcher 未在 5s 内打开 ja lang 并 reconcile"

        # 之后 /ja/search 应能命中
        r = c.post("/ja/search", json={"q": "あいまい", "limit": 10})
        assert r.status_code == 200
        assert any(h["ulid"] == "01JZDLAZJ" for h in r.json()["hits"])
