"""Authentication routes: signup, login, JWT profile and password updates.

Expects a DynamoDB users table (DDB_USERS_TABLE env var) with an
EmailIndex GSI on the ``email`` attribute.
"""

from __future__ import annotations


import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.apps.backend.deps.auth import get_current_user_id
from src.apps.backend.security.jwt_tokens import create_access_token
from src.apps.backend.security.passwords import hash_password, verify_password
from src.apps.backend.services import users_service

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class UserOut(BaseModel):
    """Public-facing user representation (no password hash)."""

    id: str
    username: str
    email: str


class AuthResponse(BaseModel):
    """Response returned after successful signup, login, or profile update."""

    access_token: str
    token_type: str = "bearer"
    user: UserOut


from src.apps.backend.validation import (
    EMAIL_MAX,
    EMAIL_PATTERN,
    PASSWORD_MAX,
    PASSWORD_MIN,
    USERNAME_MAX,
    USERNAME_MIN,
)


class SignupBody(BaseModel):
    """Request body for POST /auth/signup."""

    username: str = Field(..., min_length=USERNAME_MIN, max_length=USERNAME_MAX)
    email: str = Field(..., max_length=EMAIL_MAX, pattern=EMAIL_PATTERN)
    password: str = Field(..., min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)


class LoginBody(BaseModel):
    """Request body for POST /auth/login."""

    email: str = Field(..., max_length=EMAIL_MAX, pattern=EMAIL_PATTERN)
    password: str = Field(..., min_length=1, max_length=PASSWORD_MAX)


class ProfileBody(BaseModel):
    """Request body for PUT /auth/profile."""

    username: str = Field(..., min_length=USERNAME_MIN, max_length=USERNAME_MAX)
    email: str = Field(..., max_length=EMAIL_MAX, pattern=EMAIL_PATTERN)


class ChangePasswordBody(BaseModel):
    """Request body for POST /auth/change-password."""

    currentPassword: str = Field(..., min_length=1, max_length=PASSWORD_MAX)
    newPassword: str = Field(..., min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)


class ChangePasswordOk(BaseModel):
    """200 response for change-password (FastAPI 0.109+ rejects 204 with JSONResponse)."""

    ok: bool = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_user_out(item: dict) -> UserOut:
    """Convert a raw DynamoDB user item to a UserOut response model.

    >>> _to_user_out({"user_id": "u1", "username": "alice", "email": "a@b.com"})
    UserOut(id='u1', username='alice', email='a@b.com')
    """
    return UserOut(
        id=item["user_id"],
        username=item["username"],
        email=item["email"],
    )


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

@router.post("/signup", response_model=AuthResponse)
def signup(body: SignupBody) -> AuthResponse:
    """Register a new user account and return a JWT access token.

    Raises HTTP 409 if the email is already registered.
    """
    existing = users_service.get_user_by_email(str(body.email))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user_id = str(uuid.uuid4())
    password_hash = hash_password(body.password)
    item = users_service.create_user(
        user_id=user_id,
        email=str(body.email),
        username=body.username,
        password_hash=password_hash,
    )
    token = create_access_token(user_id)
    return AuthResponse(access_token=token, user=_to_user_out(item))


@router.post("/login", response_model=AuthResponse)
def login(body: LoginBody) -> AuthResponse:
    """Authenticate a user with email and password, returning a JWT access token.

    Raises HTTP 401 if the email is not found or the password is incorrect.
    """
    item = users_service.get_user_by_email(str(body.email))
    if not item or not verify_password(body.password, item.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(item["user_id"])
    return AuthResponse(access_token=token, user=_to_user_out(item))


@router.get("/me", response_model=UserOut)
def me(user_id: str = Depends(get_current_user_id)) -> UserOut:
    """Return the currently authenticated user's profile.

    Raises HTTP 404 if the user record no longer exists in DynamoDB.
    """
    item = users_service.get_user_by_id(user_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return _to_user_out(item)


@router.put("/profile", response_model=AuthResponse)
def update_profile(
    body: ProfileBody,
    user_id: str = Depends(get_current_user_id),
) -> AuthResponse:
    """Update the authenticated user's username and email.

    Returns a fresh JWT and the updated user profile.
    Raises HTTP 409 if the new email is already used by another account.
    """
    new_email = str(body.email).strip().lower()
    other = users_service.get_user_by_email(new_email)
    if other and other.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already in use by another account",
        )

    item = users_service.update_user_profile(user_id, body.username, str(body.email))
    token = create_access_token(user_id)
    return AuthResponse(access_token=token, user=_to_user_out(item))


@router.post("/change-password", response_model=ChangePasswordOk)
def change_password(
    body: ChangePasswordBody,
    user_id: str = Depends(get_current_user_id),
) -> ChangePasswordOk:
    """Change the authenticated user's password.

    Validates the current password before applying the new one.
    Raises HTTP 400 if the current password is incorrect.
    """
    item = users_service.get_user_by_id(user_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    if not verify_password(body.currentPassword, item.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    users_service.update_password_hash(user_id, hash_password(body.newPassword))
    return ChangePasswordOk()
