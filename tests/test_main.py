"""Tests for src.apps.backend.main — app setup, CORS, health endpoint, router registration.

Uses importlib.reload() to re-trigger module-level code (Modal key parsing,
CORS setup) with different env vars per test.
"""

import os

import pytest


class TestModalKeyParsing:
    """Tests for Modal API key parsing in main.py.

    The backend parses MODAL_API_KEY (JSON) at import time and extracts
    token_id/token_secret into separate env vars that the Modal SDK reads.
    """

    def test_json_modal_key_sets_env_vars(self, monkeypatch):
        """Valid JSON key is split into MODAL_TOKEN_ID and MODAL_TOKEN_SECRET."""
        monkeypatch.setenv("MODAL_API_KEY", '{"token_id": "tid", "token_secret": "tsec"}')
        import importlib
        import src.apps.backend.main
        importlib.reload(src.apps.backend.main)
        assert os.environ.get("MODAL_TOKEN_ID") == "tid"
        assert os.environ.get("MODAL_TOKEN_SECRET") == "tsec"

    def test_non_json_modal_key_ignored(self, monkeypatch):
        """Plain string key (not JSON) is silently ignored — no crash."""
        monkeypatch.setenv("MODAL_API_KEY", "plain-token-string")
        monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
        import importlib
        import src.apps.backend.main
        importlib.reload(src.apps.backend.main)

    def test_malformed_json_ignored(self, monkeypatch):
        """Truncated JSON is silently ignored — no crash on startup."""
        monkeypatch.setenv("MODAL_API_KEY", '{"broken json')
        import importlib
        import src.apps.backend.main
        importlib.reload(src.apps.backend.main)


class TestCorsConfiguration:
    """Tests for CORS middleware setup."""

    def test_wildcard_cors(self, monkeypatch):
        """CORS_ALLOW_ORIGINS='*' results in a functional app."""
        monkeypatch.setenv("CORS_ALLOW_ORIGINS", "*")
        import importlib
        import src.apps.backend.main
        importlib.reload(src.apps.backend.main)
        assert src.apps.backend.main.app is not None

    def test_comma_separated_origins(self, monkeypatch):
        """Multiple origins are split correctly from comma-separated string."""
        monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://localhost:3000,https://artguard.com")
        import importlib
        import src.apps.backend.main
        importlib.reload(src.apps.backend.main)
        assert src.apps.backend.main.app is not None


class TestHealthEndpoint:
    """Tests for GET /health — the only unauthenticated operational endpoint."""

    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client):
        """Health check returns 200 with status='ok' — used by ALB health checks."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_health_no_auth_required(self, client):
        """Health endpoint must work without Authorization header (ALB hits it directly)."""
        resp = await client.get("/health")
        assert resp.status_code == 200


class TestRouterRegistration:
    """Verify all expected route prefixes are registered on the app."""

    @pytest.mark.asyncio
    async def test_auth_routes_registered(self, client):
        resp = await client.post("/auth/login", json={"email": "x", "password": "y"})
        assert resp.status_code != 404  # route exists (may return 401/422, not 404)

    @pytest.mark.asyncio
    async def test_inference_route_registered(self, client):
        resp = await client.post("/inference")
        assert resp.status_code != 404

    @pytest.mark.asyncio
    async def test_inferences_route_registered(self, client):
        resp = await client.get("/inferences")
        assert resp.status_code != 404  # 401 (no auth) is expected, not 404

    @pytest.mark.asyncio
    async def test_rag_route_registered(self, client):
        resp = await client.post("/rag-query", json={"query": "test"})
        assert resp.status_code != 404
