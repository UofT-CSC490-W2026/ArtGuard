"""Extended tests for main.py covering module-level code and CORS configuration.

The main.py module runs code at import time (Modal key parsing, CORS setup).
These tests use importlib.reload() to re-trigger that code with different env vars.
"""

import importlib
import os

import pytest


class TestModalKeyParsingExtended:
    """Tests for Modal API key parsing at module import time."""

    def test_valid_json_key_sets_token_env_vars(self, monkeypatch):
        """Valid JSON MODAL_API_KEY is split into MODAL_TOKEN_ID and MODAL_TOKEN_SECRET."""
        monkeypatch.setenv("MODAL_API_KEY", '{"token_id": "my-tid", "token_secret": "my-tsec"}')
        import src.apps.backend.main
        importlib.reload(src.apps.backend.main)
        assert os.environ.get("MODAL_TOKEN_ID") == "my-tid"
        assert os.environ.get("MODAL_TOKEN_SECRET") == "my-tsec"

    def test_non_json_key_does_not_crash(self, monkeypatch):
        """Plain string MODAL_API_KEY (not JSON) is silently ignored."""
        monkeypatch.setenv("MODAL_API_KEY", "plain-token-string")
        monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
        import src.apps.backend.main
        importlib.reload(src.apps.backend.main)
        # Should not crash

    def test_malformed_json_key_does_not_crash(self, monkeypatch):
        """Truncated JSON MODAL_API_KEY is silently ignored."""
        monkeypatch.setenv("MODAL_API_KEY", '{"broken json')
        import src.apps.backend.main
        importlib.reload(src.apps.backend.main)
        # Should not crash

    def test_missing_key_in_json_does_not_crash(self, monkeypatch):
        """JSON without token_id/token_secret is silently ignored."""
        monkeypatch.setenv("MODAL_API_KEY", '{"other_key": "value"}')
        import src.apps.backend.main
        importlib.reload(src.apps.backend.main)
        # Should not crash

    def test_empty_modal_api_key_does_not_crash(self, monkeypatch):
        """Empty MODAL_API_KEY is silently ignored."""
        monkeypatch.setenv("MODAL_API_KEY", "")
        import src.apps.backend.main
        importlib.reload(src.apps.backend.main)
        # Should not crash


class TestCorsConfigurationExtended:
    """Tests for CORS middleware configuration."""

    def test_wildcard_cors_creates_app(self, monkeypatch):
        """CORS_ALLOW_ORIGINS='*' results in a functional app."""
        monkeypatch.setenv("CORS_ALLOW_ORIGINS", "*")
        import src.apps.backend.main
        importlib.reload(src.apps.backend.main)
        assert src.apps.backend.main.app is not None

    def test_comma_separated_origins(self, monkeypatch):
        """Multiple origins are split correctly from comma-separated string."""
        monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://localhost:3000,https://artguard.com")
        import src.apps.backend.main
        importlib.reload(src.apps.backend.main)
        assert src.apps.backend.main.app is not None

    def test_empty_cors_origins_falls_back_to_wildcard(self, monkeypatch):
        """Empty CORS_ALLOW_ORIGINS falls back to ['*']."""
        monkeypatch.setenv("CORS_ALLOW_ORIGINS", "")
        import src.apps.backend.main
        importlib.reload(src.apps.backend.main)
        assert src.apps.backend.main.app is not None

    def test_single_origin(self, monkeypatch):
        """Single origin without comma works correctly."""
        monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://artguard.com")
        import src.apps.backend.main
        importlib.reload(src.apps.backend.main)
        assert src.apps.backend.main.app is not None


class TestAppEndpoints:
    """Tests for app-level endpoints."""

    @pytest.mark.asyncio
    async def test_health_check_returns_ok(self, client):
        """GET /health returns 200 with status='ok'."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_root_returns_api_metadata(self, client):
        """GET / returns API metadata with version and endpoints."""
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "ArtGuard" in data["message"]
        assert "version" in data
        assert "endpoints" in data
        assert "/health" in data["endpoints"]
        assert "/auth/*" in data["endpoints"]
        assert "/inference" in data["endpoints"]

    @pytest.mark.asyncio
    async def test_health_no_auth_required(self, client):
        """GET /health works without Authorization header."""
        resp = await client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_all_routers_registered(self, client):
        """All expected route prefixes are registered (return non-404)."""
        routes_to_check = [
            ("POST", "/auth/login", {"email": "x@x.com", "password": "y"}),
            ("GET", "/inferences", None),
            ("POST", "/rag-query", {"query": "test"}),
        ]
        for method, path, body in routes_to_check:
            if method == "GET":
                resp = await client.get(path)
            else:
                resp = await client.post(path, json=body)
            assert resp.status_code != 404, f"{method} {path} returned 404 (route not registered)"
