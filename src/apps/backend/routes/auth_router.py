"""
Authentication: signup, login, JWT profile/password updates.

Expects DynamoDB users table (DDB_USERS_TABLE) with EmailIndex on `email`.
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


class UserOut(BaseModel):
    id: str
    username: str
    email: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


def _to_user_out(item: dict) -> UserOut:
    return UserOut(
        id=item["user_id"],
        username=item["username"],
        email=item["email"],
    )


_EMAIL_RE = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"


class SignupBody(BaseModel):
    username: str = Field(..., min_length=3)
    email: str = Field(..., pattern=_EMAIL_RE)
    password: str = Field(..., min_length=6)


class LoginBody(BaseModel):
    email: str = Field(..., pattern=_EMAIL_RE)
    password: str


class ProfileBody(BaseModel):
    username: str = Field(..., min_length=3)
    email: str = Field(..., pattern=_EMAIL_RE)


class ChangePasswordBody(BaseModel):
    currentPassword: str
    newPassword: str = Field(..., min_length=6)


@router.post("/signup", response_model=AuthResponse)
def signup(body: SignupBody) -> AuthResponse:
    existing = users_service.get_user_by_email(str(body.email))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user_id = str(uuid.uuid4())
    ph = hash_password(body.password)
    item = users_service.create_user(
        user_id=user_id,
        email=str(body.email),
        username=body.username,
        password_hash=ph,
    )
    token = create_access_token(user_id)
    return AuthResponse(
        access_token=token,
        user=_to_user_out(item),
    )


@router.post("/login", response_model=AuthResponse)
def login(body: LoginBody) -> AuthResponse:
    item = users_service.get_user_by_email(str(body.email))
    if not item or not verify_password(body.password, item.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(item["user_id"])
    return AuthResponse(
        access_token=token,
        user=_to_user_out(item),
    )


@router.get("/me", response_model=UserOut)
def me(user_id: str = Depends(get_current_user_id)) -> UserOut:
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
    new_email = str(body.email).strip().lower()
    other = users_service.get_user_by_email(new_email)
    if other and other.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already in use by another account",
        )

    item = users_service.update_user_profile(user_id, body.username, str(body.email))
    token = create_access_token(user_id)
    return AuthResponse(
        access_token=token,
        user=_to_user_out(item),
    )


class ChangePasswordOk(BaseModel):
    """200 JSON body — FastAPI 0.109+ rejects 204 on routes that default to JSONResponse."""

    ok: bool = True


@router.post("/change-password", response_model=ChangePasswordOk)
def change_password(
    body: ChangePasswordBody,
    user_id: str = Depends(get_current_user_id),
) -> ChangePasswordOk:
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
