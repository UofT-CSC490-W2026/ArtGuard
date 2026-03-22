"""JWT access tokens (HS256)."""

from __future__ import annotations

import os
import time
from typing import Any

import jwt

JWT_ALGORITHM = "HS256"
DEFAULT_EXPIRE_SECONDS = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_SECONDS", "3600"))


def _secret() -> str:
    secret = os.getenv("JWT_SECRET_KEY", "").strip()
    if secret:
        return secret
    if os.getenv("ENVIRONMENT", "dev").lower() in ("dev", "development", "local"):
        return "dev-only-jwt-secret-do-not-use-in-production"
    raise RuntimeError("JWT_SECRET_KEY must be set in non-dev environments")


def create_access_token(user_id: str, extra_claims: dict[str, Any] | None = None) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": user_id,
        "iat": now,
        "exp": now + DEFAULT_EXPIRE_SECONDS,
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
