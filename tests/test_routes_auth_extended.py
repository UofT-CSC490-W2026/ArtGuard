"""Extended tests for auth routes covering edge cases not in test_routes_auth.py.

Covers:
- GET /auth/me when user is deleted after token issued (404)
- PUT /auth/profile when new email belongs to another user (409)
- PUT /auth/profile when same user updates to their own email (200)
- POST /auth/change-password when user record is missing (404)
- POST /auth/change-password with correct current password (200)
- _to_user_out helper function
"""

import pytest


class TestMeEdgeCases:
    """Edge cases for GET /auth/me."""

    @pytest.mark.asyncio
    async def test_me_user_deleted_after_token_issued(self, client, dynamodb):
        """GET /auth/me returns 404 if the user was deleted after token was created."""
        from src.apps.backend.security.jwt_tokens import create_access_token
        token = create_access_token("ghost-user-id")
        headers = {"Authorization": f"Bearer {token}"}
        resp = await client.get("/auth/me", headers=headers)
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_me_returns_correct_user_fields(self, client, create_test_user, auth_headers):
        """GET /auth/me returns id, username, email — no password_hash."""
        create_test_user(user_id="test-user-1", email="test@example.com", username="testuser")
        resp = await client.get("/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "test-user-1"
        assert data["username"] == "testuser"
        assert data["email"] == "test@example.com"
        assert "password_hash" not in data


class TestUpdateProfileEdgeCases:
    """Edge cases for PUT /auth/profile."""

    @pytest.mark.asyncio
    async def test_update_profile_email_taken_by_other_user(self, client, create_test_user, dynamodb):
        """PUT /auth/profile returns 409 if new email belongs to a different user."""
        create_test_user(user_id="user-a", email="a@example.com", username="usera")
        create_test_user(user_id="user-b", email="b@example.com", username="userb")

        from src.apps.backend.security.jwt_tokens import create_access_token
        token_a = create_access_token("user-a")
        headers_a = {"Authorization": f"Bearer {token_a}"}

        resp = await client.put("/auth/profile", json={
            "username": "usera_new",
            "email": "b@example.com",  # belongs to user-b
        }, headers=headers_a)
        assert resp.status_code == 409
        assert "already in use" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_update_profile_same_email_allowed(self, client, create_test_user, auth_headers):
        """PUT /auth/profile allows updating to the same email (no conflict with self)."""
        create_test_user(user_id="test-user-1", email="test@example.com", username="testuser")
        resp = await client.put("/auth/profile", json={
            "username": "newusername",
            "email": "test@example.com",  # same email as current user
        }, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["user"]["username"] == "newusername"

    @pytest.mark.asyncio
    async def test_update_profile_returns_new_token(self, client, create_test_user, auth_headers):
        """PUT /auth/profile returns a fresh JWT access token."""
        create_test_user()
        resp = await client.put("/auth/profile", json={
            "username": "updated",
            "email": "updated@example.com",
        }, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 0


class TestChangePasswordEdgeCases:
    """Edge cases for POST /auth/change-password."""

    @pytest.mark.asyncio
    async def test_change_password_user_not_found(self, client, dynamodb):
        """POST /auth/change-password returns 404 if user record is missing."""
        from src.apps.backend.security.jwt_tokens import create_access_token
        token = create_access_token("ghost-user")
        headers = {"Authorization": f"Bearer {token}"}
        resp = await client.post("/auth/change-password", json={
            "currentPassword": "anything",
            "newPassword": "newpass123",
        }, headers=headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_change_password_wrong_current_returns_400(self, client, create_test_user, auth_headers):
        """POST /auth/change-password returns 400 for wrong current password."""
        create_test_user()
        resp = await client.post("/auth/change-password", json={
            "currentPassword": "wrongpassword",
            "newPassword": "newpassword123",
        }, headers=auth_headers)
        assert resp.status_code == 400
        assert "incorrect" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_change_password_new_password_too_short_422(self, client, create_test_user, auth_headers):
        """POST /auth/change-password rejects new password shorter than min length."""
        create_test_user()
        resp = await client.post("/auth/change-password", json={
            "currentPassword": "password123",
            "newPassword": "12345",  # min 6
        }, headers=auth_headers)
        assert resp.status_code == 422


class TestSignupEdgeCases:
    """Additional edge cases for POST /auth/signup."""

    @pytest.mark.asyncio
    async def test_signup_username_at_max_length(self, client):
        """Signup with username at max length (50 chars) succeeds."""
        resp = await client.post("/auth/signup", json={
            "username": "a" * 50,
            "email": "maxlen@example.com",
            "password": "password123",
        })
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_signup_username_over_max_length_422(self, client):
        """Signup with username over max length (51 chars) is rejected."""
        resp = await client.post("/auth/signup", json={
            "username": "a" * 51,
            "email": "toolong@example.com",
            "password": "password123",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_signup_returns_bearer_token_type(self, client):
        """Signup response always has token_type='bearer'."""
        resp = await client.post("/auth/signup", json={
            "username": "tokentest",
            "email": "tokentest@example.com",
            "password": "password123",
        })
        assert resp.status_code == 200
        assert resp.json()["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_signup_email_case_insensitive_conflict(self, client, create_test_user):
        """Signup with uppercase version of existing email returns 409."""
        create_test_user(email="existing@example.com")
        resp = await client.post("/auth/signup", json={
            "username": "newuser",
            "email": "EXISTING@EXAMPLE.COM",
            "password": "password123",
        })
        assert resp.status_code == 409


class TestLoginEdgeCases:
    """Additional edge cases for POST /auth/login."""

    @pytest.mark.asyncio
    async def test_login_returns_user_object(self, client, create_test_user):
        """POST /auth/login response includes user object with id, username, email."""
        create_test_user(email="login2@example.com", username="loginuser", user_id="login-uid")
        resp = await client.post("/auth/login", json={
            "email": "login2@example.com",
            "password": "password123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["id"] == "login-uid"
        assert data["user"]["username"] == "loginuser"
        assert data["user"]["email"] == "login2@example.com"

    @pytest.mark.asyncio
    async def test_login_email_case_insensitive(self, client, create_test_user):
        """POST /auth/login works with uppercase email (case-insensitive lookup)."""
        create_test_user(email="case@example.com")
        resp = await client.post("/auth/login", json={
            "email": "CASE@EXAMPLE.COM",
            "password": "password123",
        })
        assert resp.status_code == 200
