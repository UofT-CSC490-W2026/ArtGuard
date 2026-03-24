"""Tests for auth routes: signup, login, me, profile, change-password."""

import pytest


class TestHealthAndRoot:
    """Tests for public endpoints."""

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_root(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "ArtGuard" in data["message"]
        assert "endpoints" in data


class TestSignup:
    """Tests for POST /auth/signup."""

    @pytest.mark.asyncio
    async def test_successful_signup(self, client):
        resp = await client.post("/auth/signup", json={
            "username": "newuser",
            "email": "new@example.com",
            "password": "password123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["username"] == "newuser"
        assert data["user"]["email"] == "new@example.com"

    @pytest.mark.asyncio
    async def test_duplicate_email_409(self, client, create_test_user):
        create_test_user(email="existing@example.com")
        resp = await client.post("/auth/signup", json={
            "username": "another",
            "email": "existing@example.com",
            "password": "password123",
        })
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_short_username_422(self, client):
        resp = await client.post("/auth/signup", json={
            "username": "ab",  # min_length=3
            "email": "test@test.com",
            "password": "password123",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_email_422(self, client):
        resp = await client.post("/auth/signup", json={
            "username": "testuser",
            "email": "not-an-email",
            "password": "password123",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_short_password_422(self, client):
        resp = await client.post("/auth/signup", json={
            "username": "testuser",
            "email": "test@test.com",
            "password": "12345",  # min_length=6
        })
        assert resp.status_code == 422


class TestLogin:
    """Tests for POST /auth/login."""

    @pytest.mark.asyncio
    async def test_successful_login(self, client, create_test_user):
        create_test_user(email="login@example.com")
        resp = await client.post("/auth/login", json={
            "email": "login@example.com",
            "password": "password123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_wrong_password_401(self, client, create_test_user):
        create_test_user(email="user@example.com")
        resp = await client.post("/auth/login", json={
            "email": "user@example.com",
            "password": "wrongpassword",
        })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_nonexistent_email_401(self, client):
        resp = await client.post("/auth/login", json={
            "email": "nobody@example.com",
            "password": "password123",
        })
        assert resp.status_code == 401


class TestMe:
    """Tests for GET /auth/me."""

    @pytest.mark.asyncio
    async def test_returns_user(self, client, create_test_user, auth_headers):
        create_test_user()
        resp = await client.get("/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "test-user-1"

    @pytest.mark.asyncio
    async def test_no_auth_401(self, client):
        resp = await client.get("/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_401(self, client):
        resp = await client.get("/auth/me", headers={"Authorization": "Bearer bad-token"})
        assert resp.status_code == 401


class TestUpdateProfile:
    """Tests for PUT /auth/profile."""

    @pytest.mark.asyncio
    async def test_updates_profile(self, client, create_test_user, auth_headers):
        create_test_user()
        resp = await client.put("/auth/profile", json={
            "username": "updated",
            "email": "updated@example.com",
        }, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["user"]["username"] == "updated"


class TestChangePassword:
    """Tests for POST /auth/change-password."""

    @pytest.mark.asyncio
    async def test_successful_change(self, client, create_test_user, auth_headers):
        create_test_user()
        resp = await client.post("/auth/change-password", json={
            "currentPassword": "password123",
            "newPassword": "newpassword123",
        }, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @pytest.mark.asyncio
    async def test_wrong_current_password_400(self, client, create_test_user, auth_headers):
        create_test_user()
        resp = await client.post("/auth/change-password", json={
            "currentPassword": "wrongpassword",
            "newPassword": "newpassword123",
        }, headers=auth_headers)
        assert resp.status_code == 400
