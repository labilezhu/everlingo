from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from everlingo.gateway.user_profile_api import router
from everlingo.models import LANGUAGES


# ── Mock helpers ──────────────────────────────────────────────────


class _MockCtx:
    """Async context manager that yields a given session."""

    def __init__(self, session: Any) -> None:
        self._session = session

    async def __aenter__(self) -> Any:
        return self._session

    async def __aexit__(self, *args: Any) -> None:
        pass


def _fake_result(data: dict) -> AsyncMock:
    r = AsyncMock()
    r.content = [AsyncMock()]
    r.content[0].text = json.dumps(data)
    r.isError = False
    return r


def _error_result(text: str) -> AsyncMock:
    r = AsyncMock()
    r.content = [AsyncMock()]
    r.content[0].text = text
    r.isError = True
    return r


def _patch_workspace(mock_session: AsyncMock) -> tuple[Any, Any]:
    """Patch _workspace helper to yield mock_session (IndexerOfflineError → 503 不模拟)."""

    def _mk_workspace() -> _MockCtx:
        return _MockCtx(mock_session)

    p = patch(
        "everlingo.gateway.user_profile_api._workspace",
        side_effect=_mk_workspace,
    )
    p.start()
    return p


def _patch_workspace_503():
    """Patch _workspace to raise HTTPException 503（indexer 不可达降级）。"""
    from fastapi import HTTPException

    def _mk_workspace():
        raise HTTPException(503, detail="indexer offline")

    p = patch(
        "everlingo.gateway.user_profile_api._workspace",
        side_effect=_mk_workspace,
    )
    p.start()
    return p


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def client() -> TestClient:
    _app = FastAPI()
    _app.include_router(router)
    return TestClient(_app)


def _patch_profile(target_language: str) -> tuple[dict, Any, Any]:
    """Patch load_profile/save_profile to a stub backed by a mutable dict.

    返回 (current, p1, p2)，调用方需在 finally 中 stop 两个 patch。
    """
    from everlingo.models import UserProfile

    current = {"target_language": target_language}

    def _load() -> UserProfile:
        return UserProfile(language={"target_language": current["target_language"]})

    def _save(profile: UserProfile) -> None:
        current["target_language"] = profile.language.target_language

    p1 = patch("everlingo.gateway.user_profile_api.load_profile", side_effect=_load)
    p2 = patch("everlingo.gateway.user_profile_api.save_profile", side_effect=_save)
    p1.start()
    p2.start()
    return current, p1, p2


# ── GET /api/user-profile/status ─────────────────────────────────


class TestUserProfileStatus:
    def test_unset_target(self, client: TestClient):
        _, pp1, pp2 = _patch_profile("")
        session = AsyncMock()
        session.call_tool = AsyncMock(return_value=_fake_result({"vaults": [], "count": 0}))
        p = _patch_workspace(session)
        try:
            resp = client.get("/api/user-profile/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["target_language"] == ""
            assert data["is_valid"] is False
            assert data["needs_setup"] is True
        finally:
            p.stop()
            pp1.stop()
            pp2.stop()

    def test_valid_and_initialized(self, client: TestClient):
        _, pp1, pp2 = _patch_profile("en")
        session = AsyncMock()
        session.call_tool = AsyncMock(
            return_value=_fake_result({"vaults": ["en", "ja"], "count": 2})
        )
        p = _patch_workspace(session)
        try:
            resp = client.get("/api/user-profile/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["target_language"] == "en"
            assert data["vault_initialized"] is True
            assert data["is_valid"] is True
            assert data["needs_setup"] is False
        finally:
            p.stop()
            pp1.stop()
            pp2.stop()

    def test_valid_but_not_initialized(self, client: TestClient):
        _, pp1, pp2 = _patch_profile("de")
        session = AsyncMock()
        session.call_tool = AsyncMock(
            return_value=_fake_result({"vaults": ["en"], "count": 1})
        )
        p = _patch_workspace(session)
        try:
            resp = client.get("/api/user-profile/status")
            data = resp.json()
            assert data["vault_initialized"] is False
            assert data["is_valid"] is False
            assert data["needs_setup"] is True
        finally:
            p.stop()
            pp1.stop()
            pp2.stop()

    def test_unsupported_lang(self, client: TestClient):
        _, pp1, pp2 = _patch_profile("xx")
        session = AsyncMock()
        session.call_tool = AsyncMock(return_value=_fake_result({"vaults": ["xx"], "count": 1}))
        p = _patch_workspace(session)
        try:
            resp = client.get("/api/user-profile/status")
            data = resp.json()
            assert data["is_valid"] is False
            assert data["needs_setup"] is True
        finally:
            p.stop()
            pp1.stop()
            pp2.stop()

    def test_indexer_unreachable_degrades(self, client: TestClient):
        _, pp1, pp2 = _patch_profile("en")
        p = _patch_workspace_503()
        try:
            resp = client.get("/api/user-profile/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["vault_initialized"] is None
            assert data["is_valid"] is False
            assert data["needs_setup"] is True
        finally:
            p.stop()
            pp1.stop()
            pp2.stop()


# ── GET /api/target-language/list ────────────────────────────────


class TestTargetLanguageList:
    def test_lists_all_five_with_states(self, client: TestClient):
        _, pp1, pp2 = _patch_profile("en")
        session = AsyncMock()
        session.call_tool = AsyncMock(
            return_value=_fake_result({"vaults": ["en", "ja"], "count": 2})
        )
        p = _patch_workspace(session)
        try:
            resp = client.get("/api/target-language/list")
            assert resp.status_code == 200
            data = resp.json()
            assert data["current_default"] == "en"
            langs = {l["code"]: l for l in data["languages"]}
            assert set(langs.keys()) == set(LANGUAGES.keys())
            assert langs["en"]["is_default"] is True
            assert langs["en"]["vault_initialized"] is True
            assert langs["ja"]["vault_initialized"] is True
            assert langs["ja"]["is_default"] is False
            assert langs["fr"]["vault_initialized"] is False
            assert langs["fr"]["disabled"] is False
        finally:
            p.stop()
            pp1.stop()
            pp2.stop()

    def test_indexer_unreachable_disables_all(self, client: TestClient):
        _, pp1, pp2 = _patch_profile("en")
        p = _patch_workspace_503()
        try:
            resp = client.get("/api/target-language/list")
            assert resp.status_code == 200
            data = resp.json()
            for l in data["languages"]:
                assert l["vault_initialized"] is None
                assert l["disabled"] is True
                assert l["disabled_reason"] is not None
        finally:
            p.stop()
            pp1.stop()
            pp2.stop()


# ── POST /api/target-language/default ────────────────────────────


class TestSetDefaultLanguage:
    def test_invalid_lang_returns_400(self, client: TestClient):
        _, pp1, pp2 = _patch_profile("")
        session = AsyncMock()
        session.call_tool = AsyncMock(return_value=_fake_result({"vaults": [], "count": 0}))
        p = _patch_workspace(session)
        try:
            resp = client.post("/api/target-language/default", json={"lang": "xx"})
            assert resp.status_code == 400
            session.call_tool.assert_not_awaited()
        finally:
            p.stop()
            pp1.stop()
            pp2.stop()

    def test_initialized_lang_writes_without_create_vault(self, client: TestClient):
        current, pp1, pp2 = _patch_profile("")
        session = AsyncMock()
        # 第一次调用（list_vaults 于 default 端点内）→ vaults=[en]
        # 随后 target_language_list() 再开一次 workspace session → 需返回两次
        session.call_tool = AsyncMock(
            return_value=_fake_result({"vaults": ["en"], "count": 1})
        )
        p = _patch_workspace(session)
        try:
            resp = client.post("/api/target-language/default", json={"lang": "en"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["current_default"] == "en"
            assert current["target_language"] == "en"
            calls = [c[0] for c in session.call_tool.await_args_list]
            assert all(c[0] == "list_vaults" for c in calls)
            assert "create_vault" not in [c[0] for c in calls]
        finally:
            p.stop()
            pp1.stop()
            pp2.stop()

    def test_uninitialized_lang_creates_vault_then_writes(self, client: TestClient):
        current, pp1, pp2 = _patch_profile("")
        session = AsyncMock()
        # 第 1 次 list_vaults → 空；第 2 次 create_vault → ok；
        # target_language_list() 内第 3 次 list_vaults → 含 ja
        session.call_tool = AsyncMock(side_effect=[
            _fake_result({"vaults": [], "count": 0}),
            _fake_result({"ok": True, "lang": "ja", "files_written": 5}),
            _fake_result({"vaults": ["ja"], "count": 1}),
        ])
        p = _patch_workspace(session)
        try:
            resp = client.post("/api/target-language/default", json={"lang": "ja"})
            assert resp.status_code == 200
            assert current["target_language"] == "ja"
            calls = [c[0] for c in session.call_tool.await_args_list]
            assert calls[0][0] == "list_vaults"
            assert calls[1][0] == "create_vault"
            assert calls[2][0] == "list_vaults"
        finally:
            p.stop()
            pp1.stop()
            pp2.stop()

    def test_default_lang_uninitialized_still_creates_vault(self, client: TestClient):
        current, pp1, pp2 = _patch_profile("ja")
        session = AsyncMock()
        # 第 1 次 list_vaults → 空（lang 已为 default 但 vault 未建）；
        # 第 2 次 create_vault → ok；
        # target_language_list() 内第 3 次 list_vaults → 含 ja
        session.call_tool = AsyncMock(side_effect=[
            _fake_result({"vaults": [], "count": 0}),
            _fake_result({"ok": True, "lang": "ja", "files_written": 5}),
            _fake_result({"vaults": ["ja"], "count": 1}),
        ])
        p = _patch_workspace(session)
        try:
            resp = client.post("/api/target-language/default", json={"lang": "ja"})
            assert resp.status_code == 200
            assert current["target_language"] == "ja"
            calls = [c[0] for c in session.call_tool.await_args_list]
            assert calls[0][0] == "list_vaults"
            assert calls[1][0] == "create_vault"
            assert calls[2][0] == "list_vaults"
        finally:
            p.stop()
            pp1.stop()
            pp2.stop()

    def test_indexer_unreachable_returns_503_and_keeps_profile(self, client: TestClient):
        current, pp1, pp2 = _patch_profile("")
        p = _patch_workspace_503()
        try:
            resp = client.post("/api/target-language/default", json={"lang": "en"})
            assert resp.status_code == 503
            assert current["target_language"] == ""
        finally:
            p.stop()
            pp1.stop()
            pp2.stop()


# ── POST /api/target-language/reset-vault ────────────────────────


class TestResetVault:
    def test_initialized_lang_calls_reset_vault(self, client: TestClient):
        _, pp1, pp2 = _patch_profile("")
        session = AsyncMock()
        # reset_vault 成功后 target_language_list() 再开 session 做 list_vaults
        session.call_tool = AsyncMock(side_effect=[
            _fake_result({"ok": True, "lang": "en", "vault_path": "memory/languages/en/vault",
                          "files_reset": 11, "registered": True}),
            _fake_result({"vaults": ["en"], "count": 1}),
        ])
        p = _patch_workspace(session)
        try:
            resp = client.post("/api/target-language/reset-vault", json={"lang": "en"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["current_default"] == ""
            calls = [c[0] for c in session.call_tool.await_args_list]
            assert calls[0][0] == "reset_vault"
            assert calls[1][0] == "list_vaults"
        finally:
            p.stop()
            pp1.stop()
            pp2.stop()

    def test_invalid_lang_returns_400(self, client: TestClient):
        _, pp1, pp2 = _patch_profile("")
        session = AsyncMock()
        p = _patch_workspace(session)
        try:
            resp = client.post("/api/target-language/reset-vault", json={"lang": "xx"})
            assert resp.status_code == 400
            session.call_tool.assert_not_awaited()
        finally:
            p.stop()
            pp1.stop()
            pp2.stop()

    def test_indexer_unreachable_returns_503(self, client: TestClient):
        _, pp1, pp2 = _patch_profile("")
        p = _patch_workspace_503()
        try:
            resp = client.post("/api/target-language/reset-vault", json={"lang": "en"})
            assert resp.status_code == 503
        finally:
            p.stop()
            pp1.stop()
            pp2.stop()

    def test_reset_vault_fails_is_error_returns_500(self, client: TestClient):
        _, pp1, pp2 = _patch_profile("")
        session = AsyncMock()
        session.call_tool = AsyncMock(
            return_value=_error_result("vault not initialized, call create_vault first")
        )
        p = _patch_workspace(session)
        try:
            resp = client.post("/api/target-language/reset-vault", json={"lang": "en"})
            assert resp.status_code == 500
        finally:
            p.stop()
            pp1.stop()
            pp2.stop()


# ── save_profile 写回 yaml（真实文件） ────────────────────────────


class TestYamlWriteBack:
    def test_set_default_writes_everlingo_yaml(self, client: TestClient, monkeypatch, tmp_path):
        from everlingo import workspace as ws_mod

        monkeypatch.setattr(ws_mod, "WORKSPACE_ROOT", tmp_path)
        ws = tmp_path
        cfg = ws / "everlingo.yaml"
        cfg.write_text(
            "user_profile:\n  language:\n    interface_language: zh-CN\n    target_language: ''\n",
            encoding="utf-8",
        )
        ws_mod.init_workspace_dir(str(ws))

        session = AsyncMock()
        session.call_tool = AsyncMock(side_effect=[
            _fake_result({"vaults": ["en"], "count": 1}),
            _fake_result({"vaults": ["en"], "count": 1}),
        ])
        p = _patch_workspace(session)
        try:
            resp = client.post("/api/target-language/default", json={"lang": "en"})
            assert resp.status_code == 200
            data = cfg.read_text(encoding="utf-8")
            assert "target_language: en" in data
        finally:
            p.stop()
            ws_mod.init_workspace_dir(None)
