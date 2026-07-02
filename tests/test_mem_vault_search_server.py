# ref: docs/impl-spec/search/memory-vault-search-spec.md — server.py
# 用 FastAPI TestClient 直接驱动 ASGI app，不真正起 uvicorn / unix socket。
# 覆盖 5 个端点：POST /search, POST /index, POST /delete, POST /rebuild, GET /status

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from everlingo.mem.vault.search.indexer import count_chunks, count_docs
from everlingo.mem.vault.search.server import AppState, create_app


@pytest.fixture
def memory_root(tmp_path: Path) -> Path:
    root = tmp_path / "memory"
    root.mkdir()
    return root


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "index" / "memory.sqlite"


@pytest.fixture
def sock_path(tmp_path: Path) -> Path:
    return tmp_path / "index" / "indexer.sock"


@pytest.fixture
def state(db_path: Path, memory_root: Path, sock_path: Path) -> AppState:
    return AppState(db_path=db_path, memory_root=memory_root, socket_path=sock_path)


@pytest.fixture
def app(state: AppState):
    return create_app(state)


@pytest.fixture
def client(app, state):
    # TestClient 触发 lifespan（state.open / state.close）
    with TestClient(app) as c:
        yield c


def _write_item(memory_root: Path, name: str, ulid: str, body: str = "x") -> Path:
    p = memory_root / "en" / "items" / "vocab" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\nulid: {ulid}\nslug: {name.split('--')[0]}\ntype: vocab\ntitle: aimai\n---\n\n{body}", encoding="utf-8")
    return p


def test_status_after_open(client, state):
    r = client.get("/status")
    assert r.status_code == 200
    data = r.json()
    assert data["running"] is True
    assert data["docs"] == 0
    assert data["chunks"] == 0
    # 新增字段存在；具体值依赖环境（OPENAI_EMBEDDING_MODEL 是否配）。
    assert "embedded_chunks" in data
    assert "embedding_model_id" in data
    assert "embedding_dim" in data


def test_index_then_search(client, state, memory_root: Path):
    _write_item(memory_root, "aimai--01JZD0001.md", "01JZD0001", body="あいまい means ambiguous in Japanese")
    rel = "en/items/vocab/aimai--01JZD0001.md"
    r = client.post("/index", json={"path": rel})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert count_docs(state.conn) == 1

    r = client.post("/search", json={"q": "ambiguous", "limit": 10})
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 1
    assert any(h["ulid"] == "01JZD0001" for h in data["hits"])


def test_delete(client, state, memory_root: Path):
    _write_item(memory_root, "x--01JZD0002.md", "01JZD0002")
    client.post("/index", json={"path": "en/items/vocab/x--01JZD0002.md"})
    assert count_docs(state.conn) == 1
    r = client.post("/delete", json={"path": "en/items/vocab/x--01JZD0002.md"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert count_docs(state.conn) == 0


def test_rebuild(client, state, memory_root: Path):
    _write_item(memory_root, "y--01JZD0003.md", "01JZD0003")
    client.post("/index", json={"path": "en/items/vocab/y--01JZD0003.md"})
    r = client.post("/rebuild")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["indexed"] == 1
    assert count_chunks(state.conn) >= 1


def test_index_missing_file_returns_404(client, state):
    r = client.post("/index", json={"path": "en/items/vocab/nonexistent--01JZZ.md"})
    assert r.status_code == 404


def test_embed_endpoint_returns_valid_response(client, state):
    """/embed 端点存在且返回结构合法。env 配了 model 时 ok=True，否则 False。"""
    r = client.post("/embed", json={})
    assert r.status_code == 200
    data = r.json()
    assert "ok" in data
    assert "total_chunks" in data
    assert "embedded_chunks" in data
    assert "embedding_model_id" in data
    assert "embedding_dim" in data
    assert "took_ms" in data
