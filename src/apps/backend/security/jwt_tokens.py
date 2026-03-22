"""JWT access token creation and verification (HS256).

Tokens are signed with the ``JWT_SECRET_KEY`` environment variable.
In dev/local environments a fallback secret is used if the env var is unset.
"""

from __future__ import annotations

import os
import time
from typing import Any

import jwt

JWT_ALGORITHM = "HS256"
DEFAULT_EXPIRE_SECONDS = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_SECONDS", "3600"))


def _secret() -> str:
    """Return the JWT signing secret.

    Reads from the ``JWT_SECRET_KEY`` environment variable. Falls back to a
    hard-coded dev-only secret when running in dev/local environments.

    Raises:
        RuntimeError: If no secret is set in a non-dev environment.
    """
    secret = os.getenv("JWT_SECRET_KEY", "").strip()
    if secret:
        return secret
    if os.getenv("ENVIRONMENT", "dev").lower() in ("dev", "development", "local"):
        return "dev-only-jwt-secret-do-not-use-in-production"
    raise RuntimeError("JWT_SECRET_KEY must be set in non-dev environments")


def create_access_token(
    user_id: str, extra_claims: dict[str, Any] | None = None
) -> str:
    """Create a signed JWT access token for the given user.

    The token contains ``sub`` (user_id), ``iat``, ``exp``, and ``type``
    claims. Additional claims can be merged via extra_claims.

    >>> token = create_access_token("user-123")
    >>> isinstance(token, str) and len(token) > 0
    True

    Args:
        user_id:      The user identifier stored in the ``sub`` claim.
        extra_claims: Optional dict of additional claims to include.

    Returns:
        An encoded JWT string.
    """
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
    """Decode and verify a JWT access token.

    Validates the signature and expiration. Returns the decoded payload dict.

    Args:
        token: The encoded JWT string.

    Returns:
        The decoded claims dict (includes ``sub``, ``iat``, ``exp``, etc.).

    Raises:
        jwt.ExpiredSignatureError: If the token has expired.
        jwt.InvalidTokenError:     If the token is malformed or signature is invalid.
    """
    return jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
