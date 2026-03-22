"""Tests for src.apps.backend.services.users_service — DynamoDB user CRUD.

Tests verify that DynamoDB items contain all expected fields with correct
values, not just that they're non-None. Email case-insensitivity and
whitespace handling are tested because the GSI query depends on normalized
email values.
"""

import time

import pytest

from src.apps.backend.services import users_service


class TestGetUserByEmail:
    """Tests for get_user_by_email."""

    def test_returns_user_with_all_fields(self, dynamodb, create_test_user):
        """Verify the returned user dict has the full schema, not just email."""
        create_test_user(email="alice@example.com", username="alice", user_id="uid-alice")
        result = users_service.get_user_by_email("alice@example.com")
        assert result is not None
        assert result["email"] == "alice@example.com"
        assert result["user_id"] == "uid-alice"
        assert result["username"] == "alice"
        assert "password_hash" in result
        assert "created_at" in result

    def test_case_insensitive(self, dynamodb, create_test_user):
        """Email lookup is case-insensitive (GSI stores lowercase)."""
        create_test_user(email="bob@example.com")
        result = users_service.get_user_by_email("BOB@EXAMPLE.COM")
        assert result is not None
        assert result["email"] == "bob@example.com"

    def test_returns_none_when_not_found(self, dynamodb):
        result = users_service.get_user_by_email("nobody@example.com")
        assert result is None

    def test_strips_whitespace(self, dynamodb, create_test_user):
        """Leading/trailing whitespace is stripped before querying the GSI."""
        create_test_user(email="test@example.com")
        result = users_service.get_user_by_email("  test@example.com  ")
        assert result is not None
        assert result["email"] == "test@example.com"


class TestGetUserById:
    """Tests for get_user_by_id."""

    def test_returns_user_when_found(self, dynamodb, create_test_user):
        create_test_user(user_id="uid-123")
        result = users_service.get_user_by_id("uid-123")
        assert result is not None
        assert result["user_id"] == "uid-123"

    def test_returns_none_when_not_found(self, dynamodb):
        result = users_service.get_user_by_id("nonexistent")
        assert result is None


class TestCreateUser:
    """Tests for create_user."""

    def test_creates_user_with_all_fields(self, dynamodb):
        """Verify the full record is returned and persisted correctly."""
        item = users_service.create_user(
            user_id="new-1",
            email="new@example.com",
            username="newuser",
            password_hash="$2b$hashed",
        )
        assert item["user_id"] == "new-1"
        assert item["email"] == "new@example.com"
        assert item["username"] == "newuser"
        assert item["password_hash"] == "$2b$hashed"
        # created_at should be a recent Unix-ms timestamp
        assert abs(item["created_at"] - time.time() * 1000) < 5000

    def test_email_stored_lowercase(self, dynamodb):
        """Emails are normalized to lowercase for consistent GSI lookups."""
        item = users_service.create_user(
            user_id="new-2",
            email="UPPER@EXAMPLE.COM",
            username="test",
            password_hash="hash",
        )
        assert item["email"] == "upper@example.com"

    def test_duplicate_user_id_raises(self, dynamodb):
        users_service.create_user("dup-1", "a@b.com", "u1", "hash1")
        with pytest.raises(ValueError, match="already exists"):
            users_service.create_user("dup-1", "c@d.com", "u2", "hash2")


class TestUpdateUserProfile:
    """Tests for update_user_profile."""

    def test_updates_username_and_email(self, dynamodb, create_test_user):
        create_test_user(user_id="upd-1", email="old@example.com", username="oldname")
        result = users_service.update_user_profile("upd-1", "newname", "new@example.com")
        assert result["username"] == "newname"
        assert result["email"] == "new@example.com"

    def test_sets_updated_at_after_created_at(self, dynamodb, create_test_user):
        """updated_at must exist and be >= created_at after a profile update."""
        created = create_test_user(user_id="upd-2", email="ts@example.com", username="ts")
        result = users_service.update_user_profile("upd-2", "newname", "ts@example.com")
        assert "updated_at" in result
        assert result["updated_at"] >= created["created_at"]


class TestUpdatePasswordHash:
    """Tests for update_password_hash."""

    def test_updates_password_and_sets_updated_at(self, dynamodb, create_test_user):
        """Password hash is replaced and updated_at is set."""
        create_test_user(user_id="pw-1")
        users_service.update_password_hash("pw-1", "$2b$new-hash")
        user = users_service.get_user_by_id("pw-1")
        assert user["password_hash"] == "$2b$new-hash"
        assert "updated_at" in user
        assert user["updated_at"] > 0
