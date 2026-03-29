"""Tests for inference history routes: list, get, delete, stats.

Uses a helper factory to seed DynamoDB inference records, then tests
user isolation (each user only sees their own data), cursor-based
pagination, response field normalization (Decimal -> float), and
all CRUD operations.
"""

import time
from decimal import Decimal

import pytest


def _create_inference(dynamodb, inference_id, user_id="test-user-1", **overrides):
    """Helper to insert an inference record into DynamoDB.

    Accepts **overrides to customize any field for edge-case tests
    (e.g., prediction=-1 for pending, missing fields, etc.).
    """
    item = {
        "inference_id": inference_id,
        "user_id": user_id,
        "created_at": int(time.time() * 1000),
        "score": Decimal("0.85"),
        "prediction": 1,
        "inference_status": "completed",
        "artist_name": "Test Artist",
        "artwork_name": "Test Artwork",
        "image_name": "test.jpg",
        "file_size": 1024,
        "image_path": "",
    }
    item.update(overrides)
    table = dynamodb.Table("test-inferences")
    table.put_item(Item=item)


class TestInferenceStats:
    """Tests for GET /inferences/stats."""

    @pytest.mark.asyncio
    async def test_returns_zero_for_new_user(self, client, auth_headers):
        resp = await client.get("/inferences/stats", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    @pytest.mark.asyncio
    async def test_counts_user_inferences(self, client, auth_headers, dynamodb):
        _create_inference(dynamodb, "inf-1")
        _create_inference(dynamodb, "inf-2")
        _create_inference(dynamodb, "inf-other", user_id="other-user")

        resp = await client.get("/inferences/stats", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 2

    @pytest.mark.asyncio
    async def test_no_auth_401(self, client):
        resp = await client.get("/inferences/stats")
        assert resp.status_code == 401


class TestListInferences:
    """Tests for GET /inferences."""

    @pytest.mark.asyncio
    async def test_empty_list(self, client, auth_headers):
        resp = await client.get("/inferences", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["next_cursor"] is None

    @pytest.mark.asyncio
    async def test_returns_user_inferences(self, client, auth_headers, dynamodb):
        _create_inference(dynamodb, "inf-1")
        resp = await client.get("/inferences", headers=auth_headers)
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["inference_id"] == "inf-1"

    @pytest.mark.asyncio
    async def test_does_not_return_other_users(self, client, auth_headers, dynamodb):
        _create_inference(dynamodb, "other-inf", user_id="other-user")
        resp = await client.get("/inferences", headers=auth_headers)
        assert resp.json()["items"] == []

    @pytest.mark.asyncio
    async def test_limit_param(self, client, auth_headers, dynamodb):
        for i in range(5):
            _create_inference(dynamodb, f"inf-{i}")
        resp = await client.get("/inferences?limit=2", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 2

    @pytest.mark.asyncio
    async def test_invalid_cursor_400(self, client, auth_headers):
        resp = await client.get("/inferences?cursor=not-valid-base64!!!", headers=auth_headers)
        assert resp.status_code == 400


class TestGetInference:
    """Tests for GET /inferences/{inference_id}."""

    @pytest.mark.asyncio
    async def test_returns_inference_with_full_structure(self, client, auth_headers, dynamodb):
        """Verify the response includes all expected fields with correct types."""
        _create_inference(dynamodb, "get-inf-1")
        resp = await client.get("/inferences/get-inf-1", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["inference_id"] == "get-inf-1"
        assert data["artist_name"] == "Test Artist"
        assert data["artwork_name"] == "Test Artwork"
        assert isinstance(data["score"], float)  # Decimal must be serialized as float
        assert data["prediction"] in (0, 1, -1, None)
        assert data["inference_status"] == "completed"

    @pytest.mark.asyncio
    async def test_returns_patch_data_and_dimensions_when_stored(self, client, auth_headers, dynamodb):
        """Heatmap data persisted on completion is returned for history/detail views."""
        table = dynamodb.Table("test-inferences")
        table.put_item(Item={
            "inference_id": "patch-inf-1",
            "user_id": "test-user-1",
            "created_at": int(time.time() * 1000),
            "score": Decimal("0.72"),
            "prediction": 1,
            "inference_status": "completed",
            "artist_name": "A",
            "artwork_name": "B",
            "image_name": "x.jpg",
            "file_size": 100,
            "image_path": "",
            "image_width": 800,
            "image_height": 600,
            "patch_data": [
                {"x": 0, "y": 0, "w": 100, "h": 100, "prob": Decimal("0.9")},
                {"x": 100, "y": 0, "w": 100, "h": 100, "prob": Decimal("0.1")},
            ],
        })
        resp = await client.get("/inferences/patch-inf-1", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["image_width"] == 800
        assert data["image_height"] == 600
        assert len(data["patch_data"]) == 2
        assert data["patch_data"][0]["prob"] == pytest.approx(0.9)
        assert data["patch_data"][1]["x"] == 100

        list_resp = await client.get("/inferences", headers=auth_headers)
        assert list_resp.status_code == 200
        items = list_resp.json()["items"]
        assert len(items) == 1
        assert items[0]["image_width"] == 800
        assert len(items[0]["patch_data"]) == 2

    @pytest.mark.asyncio
    async def test_patch_data_skips_non_dict_and_malformed_entries(self, client, auth_headers, dynamodb):
        """Non-dict patch rows are ignored; malformed dicts are skipped without failing the request."""
        table = dynamodb.Table("test-inferences")
        table.put_item(Item={
            "inference_id": "patch-skip-1",
            "user_id": "test-user-1",
            "created_at": int(time.time() * 1000),
            "score": Decimal("0.5"),
            "prediction": 1,
            "inference_status": "completed",
            "artist_name": "A",
            "artwork_name": "B",
            "image_name": "x.jpg",
            "file_size": 100,
            "image_path": "",
            "image_width": 10,
            "image_height": 10,
            "patch_data": [
                "not-a-dict",
                {"x": 0, "y": 0, "w": 5, "h": 5, "prob": Decimal("0.7")},
                {"x": 1, "y": 1},
                {"x": 0, "y": 0, "w": 1, "h": 1, "prob": "not-a-float"},
            ],
        })
        resp = await client.get("/inferences/patch-skip-1", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["patch_data"] is not None
        assert len(data["patch_data"]) == 1
        assert data["patch_data"][0]["prob"] == pytest.approx(0.7)

    @pytest.mark.asyncio
    async def test_patch_data_all_invalid_yields_null(self, client, auth_headers, dynamodb):
        """When every patch entry is unusable, patch_data is omitted from the response."""
        table = dynamodb.Table("test-inferences")
        table.put_item(Item={
            "inference_id": "patch-all-bad",
            "user_id": "test-user-1",
            "created_at": int(time.time() * 1000),
            "score": Decimal("0.5"),
            "prediction": 1,
            "inference_status": "completed",
            "artist_name": "A",
            "artwork_name": "B",
            "image_name": "x.jpg",
            "file_size": 100,
            "image_path": "",
            "patch_data": [42, {"w": 1}],
        })
        resp = await client.get("/inferences/patch-all-bad", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json().get("patch_data") in (None, [])

    @pytest.mark.asyncio
    async def test_pending_inference_returns_prediction_negative_one(self, client, auth_headers, dynamodb):
        """Inference records still processing have prediction=-1 (pending)."""
        _create_inference(dynamodb, "pending-1", prediction=-1, inference_status="processing")
        resp = await client.get("/inferences/pending-1", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["prediction"] == -1

    @pytest.mark.asyncio
    async def test_not_found_404(self, client, auth_headers):
        resp = await client.get("/inferences/nonexistent", headers=auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_other_users_inference_404(self, client, auth_headers, dynamodb):
        """User isolation: cannot access another user's inference by ID."""
        _create_inference(dynamodb, "other-inf", user_id="other-user")
        resp = await client.get("/inferences/other-inf", headers=auth_headers)
        assert resp.status_code == 404


class TestDeleteInference:
    """Tests for DELETE /inferences/{inference_id}."""

    @pytest.mark.asyncio
    async def test_deletes_inference(self, client, auth_headers, dynamodb):
        _create_inference(dynamodb, "del-1")
        resp = await client.delete("/inferences/del-1", headers=auth_headers)
        assert resp.status_code == 204

        # Verify deleted
        resp2 = await client.get("/inferences/del-1", headers=auth_headers)
        assert resp2.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_404(self, client, auth_headers):
        resp = await client.delete("/inferences/nonexistent", headers=auth_headers)
        assert resp.status_code == 404


class TestDeleteAllInferences:
    """Tests for DELETE /inferences."""

    @pytest.mark.asyncio
    async def test_deletes_all(self, client, auth_headers, dynamodb):
        for i in range(3):
            _create_inference(dynamodb, f"bulk-{i}")
        resp = await client.delete("/inferences", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 3

    @pytest.mark.asyncio
    async def test_does_not_delete_other_users(self, client, auth_headers, dynamodb):
        _create_inference(dynamodb, "mine")
        _create_inference(dynamodb, "theirs", user_id="other-user")
        resp = await client.delete("/inferences", headers=auth_headers)
        assert resp.json()["deleted"] == 1

        # Other user's inference should still exist
        table = dynamodb.Table("test-inferences")
        result = table.get_item(Key={"inference_id": "theirs"})
        assert "Item" in result
