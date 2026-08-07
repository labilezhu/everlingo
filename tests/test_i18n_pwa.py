# ref: docs/ADR/20260807-pwa-i18n.md §3.2/§3.7 — PWA 信息 i18n（Phase 5）

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from everlingo.i18n.pwa import (
    FALLBACK_LANG,
    PWA_MANIFEST_TEXT,
    manifest_text,
    parse_accept_language,
    resolve_manifest_language,
)


class TestParseAcceptLanguage:
    def test_empty_returns_none(self):
        assert parse_accept_language("") is None
        assert parse_accept_language(None) is None

    def test_single_zh_cn(self):
        assert parse_accept_language("zh-CN") == "zh-CN"

    def test_single_en(self):
        assert parse_accept_language("en") == "en"

    def test_zh_prefix_matches_zh_cn(self):
        assert parse_accept_language("zh") == "zh-CN"
        assert parse_accept_language("zh-Hans") == "zh-CN"

    def test_en_prefix_matches_en(self):
        assert parse_accept_language("en-US") == "en"

    def test_first_matching_wins(self):
        assert parse_accept_language("zh-CN,en;q=0.8") == "zh-CN"

    def test_q_value_order(self):
        # en 排在 zh 后但 q 更高，应按 q 优先
        assert parse_accept_language("zh-CN;q=0.5,en;q=0.9") == "en"

    def test_q_zero_skip(self):
        # q=0 表示不接受，跳过；落到兜底 en
        assert parse_accept_language("zh-CN;q=0,en") == "en"

    def test_no_match_returns_none(self):
        assert parse_accept_language("ja,fr;q=0.9") is None

    def test_underscore_normalized(self):
        assert parse_accept_language("zh_CN") == "zh-CN"


class TestResolveManifestLanguage:
    def test_interface_language_priority(self):
        assert resolve_manifest_language("zh-CN", "en") == "en"

    def test_interface_language_only_if_valid(self):
        # interface_language 非法 → 回退 Accept-Language
        assert resolve_manifest_language("zh-CN", "fr") == "zh-CN"

    def test_accept_language_fallback(self):
        assert resolve_manifest_language("zh-CN") == "zh-CN"

    def test_default_en(self):
        assert resolve_manifest_language(None) == "en"

    def test_ws_router_no_profile_uses_accept(self):
        # ws_router 不传 interface_language，仅依赖 Accept-Language
        assert resolve_manifest_language("zh-CN", None) == "zh-CN"
        assert resolve_manifest_language("en", None) == "en"


class TestManifestText:
    def test_zh(self):
        assert manifest_text("zh-CN", "short_name") == "小记"

    def test_en(self):
        assert manifest_text("en", "short_name") == "Nori"

    def test_unknown_lang_falls_back_en(self):
        assert manifest_text("ja", "short_name") == manifest_text("en", "short_name")

    def test_all_languages_have_same_keys(self):
        key_sets = [frozenset(m.keys()) for m in PWA_MANIFEST_TEXT.values()]
        assert all(ks == key_sets[0] for ks in key_sets[1:])

    def test_fallback_lang_is_present(self):
        assert "en" in PWA_MANIFEST_TEXT


class TestWsRouterManifestEndpoint:
    """WS-Router 的 /manifest.webmanifest 动态协商 + /login HTML 占位符替换。"""

    @pytest.fixture
    def static_dist(self, tmp_path: Path, monkeypatch):
        import everlingo.ws_router.app as router_module

        dist = tmp_path / "dist"
        dist.mkdir(parents=True)
        (dist / "manifest.webmanifest").write_text(
            json.dumps({"start_url": "/", "display": "standalone"})
        )
        (dist / "login.html").write_text(
            '<meta name="apple-mobile-web-app-title" content="{{pwa_short_name}}" />'
        )
        monkeypatch.setattr(router_module, "_static_dir", lambda: str(dist))
        return dist

    def _client(self):
        from everlingo.ws_router.app import create_app
        from everlingo.ws_router.config import RouterConfig

        config = RouterConfig(
            jwt_secret="test-jwt-secret",
            master_secret="test-master-secret",
            master_url="http://localhost:8101",
        )
        from fastapi.testclient import TestClient

        return TestClient(create_app(config))

    def test_manifest_zh_by_accept_language(self, static_dist):
        client = self._client()
        resp = client.get("/manifest.webmanifest", headers={"Accept-Language": "zh-CN"})
        assert resp.status_code == 200
        assert resp.json()["name"] == PWA_MANIFEST_TEXT["zh-CN"]["name"]
        assert resp.json()["short_name"] == "小记"
        assert resp.headers["vary"] == "Accept-Language"
        assert resp.headers["cache-control"] == "no-cache"

    def test_manifest_en_by_default(self, static_dist):
        client = self._client()
        resp = client.get("/manifest.webmanifest")
        assert resp.status_code == 200
        assert resp.json()["name"] == PWA_MANIFEST_TEXT["en"]["name"]

    def test_manifest_preserves_language_agnostic_fields(self, static_dist):
        client = self._client()
        resp = client.get("/manifest.webmanifest", headers={"Accept-Language": "en"})
        data = resp.json()
        assert data["start_url"] == "/"
        assert data["display"] == "standalone"

    def test_login_html_placeholder_replaced(self, static_dist):
        client = self._client()
        resp = client.get("/login", headers={"Accept-Language": "zh-CN"})
        assert resp.status_code == 200
        assert "小记" in resp.text
        assert "{{pwa_short_name}}" not in resp.text
        assert resp.headers["vary"] == "Accept-Language"

    def test_login_html_default_en(self, static_dist):
        client = self._client()
        resp = client.get("/login")
        assert resp.status_code == 200
        assert PWA_MANIFEST_TEXT["en"]["short_name"] in resp.text


class TestWebAcceptorManifestEndpoint:
    """web_acceptor（单用户）的 manifest 端点：profile 优先 + Accept-Language 兜底。"""

    @pytest.fixture
    def static_dist(self, tmp_path: Path, monkeypatch):
        import everlingo.gateway.web_acceptor as acceptor_module

        dist = tmp_path / "dist"
        dist.mkdir(parents=True)
        (dist / "manifest.webmanifest").write_text(
            json.dumps({"start": "/", "display": "standalone"})
        )
        (dist / "index.html").write_text(
            '<meta name="apple-mobile-web-app-title" content="{{pwa_short_name}}" />'
        )
        monkeypatch.setattr(acceptor_module, "_static_dir", lambda: str(dist))
        return dist

    def test_profile_priority_over_accept_language(self, static_dist, monkeypatch):
        import everlingo.gateway.web_acceptor as wa_module
        from fastapi.testclient import TestClient

        profile = MagicMock()
        profile.language.interface_language = "en"
        monkeypatch.setattr(wa_module, "load_profile", lambda: profile)

        client = TestClient(wa_module.app)
        resp = client.get("/manifest.webmanifest", headers={"Accept-Language": "zh-CN"})
        assert resp.status_code == 200
        assert resp.json()["name"] == PWA_MANIFEST_TEXT["en"]["name"]
        assert resp.headers["vary"] == "Accept-Language"

    def test_profile_empty_uses_accept_language(self, static_dist, monkeypatch):
        import everlingo.gateway.web_acceptor as wa_module
        from fastapi.testclient import TestClient

        profile = MagicMock()
        profile.language.interface_language = ""
        monkeypatch.setattr(wa_module, "load_profile", lambda: profile)

        client = TestClient(wa_module.app)
        resp = client.get("/manifest.webmanifest", headers={"Accept-Language": "zh-CN"})
        assert resp.json()["short_name"] == "小记"

    def test_html_index_placeholder_replaced(self, static_dist, monkeypatch):
        import everlingo.gateway.web_acceptor as wa_module
        from fastapi.testclient import TestClient

        profile = MagicMock()
        profile.language.interface_language = "zh-CN"
        monkeypatch.setattr(wa_module, "load_profile", lambda: profile)

        client = TestClient(wa_module.app)
        resp = client.get("/")
        assert "小记" in resp.text
        assert "{{pwa_short_name}}" not in resp.text
        assert resp.headers["vary"] == "Accept-Language"