"""Tests for security modules: passwords, JWT tokens, auth dependency."""

import time
from unittest.mock import patch

import jwt
import pytest

from src.apps.backend.security.passwords import hash_password, verify_password
from src.apps.backend.security.jwt_tokens import (
    JWT_ALGORITHM,
    _secret,
    create_access_token,
    decode_access_token,
)
from src.apps.backend.deps.auth import get_current_user_id


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

class TestHashPassword:
    """Tests for hash_password."""

    def test_returns_bcrypt_hash(self):
        hashed = hash_password("my-secret")
        assert hashed.startswith("$2b$")

    def test_different_passwords_different_hashes(self):
        h1 = hash_password("password1")
        h2 = hash_password("password2")
        assert h1 != h2

    def test_same_password_different_salts(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # bcrypt uses random salt each time

    def test_empty_password(self):
        hashed = hash_password("")
        assert hashed.startswith("$2b$")

    def test_unicode_password(self):
        hashed = hash_password("пароль123")
        assert hashed.startswith("$2b$")


class TestVerifyPassword:
    """Tests for verify_password."""

    def test_correct_password(self):
        hashed = hash_password("correct")
        assert verify_password("correct", hashed) is True

    def test_wrong_password(self):
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False

    def test_malformed_hash_returns_false(self):
        assert verify_password("test", "not-a-bcrypt-hash") is False

    def test_empty_hash_returns_false(self):
        assert verify_password("test", "") is False


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------

class TestJwtSecret:
    """Tests for _secret."""

    def test_uses_env_var_when_set(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET_KEY", "my-prod-secret")
        assert _secret() == "my-prod-secret"

    def test_dev_fallback(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET_KEY", "")
        monkeypatch.setenv("ENVIRONMENT", "dev")
        assert "dev-only" in _secret()

    def test_raises_in_production(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET_KEY", "")
        monkeypatch.setenv("ENVIRONMENT", "production")
        with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
            _secret()


class TestCreateAccessToken:
    """Tests for create_access_token."""

    def test_returns_string(self):
        token = create_access_token("user-123")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_contains_correct_claims(self):
        token = create_access_token("user-456")
        payload = decode_access_token(token)
        assert payload["sub"] == "user-456"
        assert payload["type"] == "access"
        assert "iat" in payload
        assert "exp" in payload

    def test_extra_claims_merged(self):
        token = create_access_token("user-789", extra_claims={"role": "admin"})
        payload = decode_access_token(token)
        assert payload["role"] == "admin"
        assert payload["sub"] == "user-789"

    def test_token_not_expired_immediately(self):
        token = create_access_token("user-1")
        payload = decode_access_token(token)
        assert payload["exp"] > time.time()


class TestDecodeAccessToken:
    """Tests for decode_access_token."""

    def test_valid_token(self):
        token = create_access_token("user-1")
        payload = decode_access_token(token)
        assert payload["sub"] == "user-1"

    def test_expired_token_raises(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
        # Create a token that expired 10 seconds ago
        payload = {
            "sub": "user-1",
            "iat": int(time.time()) - 100,
            "exp": int(time.time()) - 10,
            "type": "access",
        }
        token = jwt.encode(payload, "test-secret", algorithm=JWT_ALGORITHM)
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_access_token(token)

    def test_invalid_signature_raises(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET_KEY", "correct-secret")
        payload = {"sub": "user-1", "exp": int(time.time()) + 3600}
        token = jwt.encode(payload, "wrong-secret", algorithm=JWT_ALGORITHM)
        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token(token)

    def test_malformed_token_raises(self):
        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token("not.a.valid.jwt")


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

class TestGetCurrentUserId:
    """Tests for the get_current_user_id FastAPI dependency."""

    def test_valid_bearer_token(self):
        token = create_access_token("user-42")
        result = get_current_user_id(f"Bearer {token}")
        assert result == "user-42"

    def test_valid_bearer_token_sets_context_user_id(self):
        """Successful auth sets the logging context user_id (lines 58-60 in auth.py)."""
        from src.apps.backend.logging_config import get_context_user_id, set_context_user_id
        set_context_user_id("")  # reset
        token = create_access_token("user-ctx-99")
        get_current_user_id(f"Bearer {token}")
        assert get_context_user_id() == "user-ctx-99"
        set_context_user_id("")  # cleanup

    def test_missing_header_raises_401(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            get_current_user_id(None)
        assert exc_info.value.status_code == 401

    def test_no_bearer_prefix_raises_401(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            get_current_user_id("Token abc")
        assert exc_info.value.status_code == 401

    def test_empty_bearer_raises_401(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            get_current_user_id("Bearer ")
        assert exc_info.value.status_code == 401

    def test_expired_token_raises_401(self, monkeypatch):
        from fastapi import HTTPException
        monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
        payload = {"sub": "user-1", "iat": 1, "exp": 2, "type": "access"}
        token = jwt.encode(payload, "test-secret", algorithm="HS256")
        with pytest.raises(HTTPException) as exc_info:
            get_current_user_id(f"Bearer {token}")
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    def test_invalid_sub_raises_401(self, monkeypatch):
        from fastapi import HTTPException
        monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
        payload = {"sub": "", "iat": int(time.time()), "exp": int(time.time()) + 3600}
        token = jwt.encode(payload, "test-secret", algorithm="HS256")
        with pytest.raises(HTTPException) as exc_info:
            get_current_user_id(f"Bearer {token}")
        assert exc_info.value.status_code == 401
