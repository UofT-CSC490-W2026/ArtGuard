"""FastAPI dependency for extracting the authenticated user ID from a Bearer JWT.

Used by route handlers via ``Depends(get_current_user_id)`` to enforce
authentication and retrieve the caller's user_id from the token's ``sub`` claim.
"""

from __future__ import annotations

import logging

import jwt
from fastapi import Header, HTTPException, status

from src.apps.backend.logging_config import set_context_user_id

logger = logging.getLogger(__name__)


def get_current_user_id(authorization: str | None = Header(None)) -> str:
    """Extract and validate the user ID from the Authorization header.

    Expects a header in the form ``Bearer <jwt-token>``. Decodes the JWT,
    validates its signature and expiration, and returns the ``sub`` claim.
    Also sets the user_id in the logging context for correlation.

    Args:
        authorization: The raw ``Authorization`` header value injected by
                       FastAPI's Header dependency.

    Returns:
        The authenticated user's ID (the ``sub`` claim from the JWT).

    Raises:
        HTTPException (401): If the header is missing, malformed, expired,
                             or contains an invalid token.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty bearer token",
        )
    try:
        from src.apps.backend.security.jwt_tokens import decode_access_token

        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        logger.info("Rejected expired token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        ) from None
    except jwt.InvalidTokenError:
        logger.warning("Rejected invalid token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from None

    sub = payload.get("sub")
    if not sub or not isinstance(sub, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
        )

    # Set user_id in logging context for request correlation
    set_context_user_id(sub)
    return sub
