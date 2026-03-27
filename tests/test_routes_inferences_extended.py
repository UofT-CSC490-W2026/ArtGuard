"""Extended tests for inference history routes covering edge cases.

Covers:
- Cursor encoding/decoding helpers
- _float_score with various input types
- _item_to_list_item with presign failure
- Pagination with cursor
- Missing DDB_INFERENCES_TABLE env var
- Inference with non-numeric prediction value
- GET /inferences/{id} with image_path presign
"""

import time
from decimal import Decimal
from unittest.mock import patch

import pytest


def _create_inference(dynamodb, inference_id, user_id="test-user-1", **overrides):
    """Helper to insert an inference record into DynamoDB."""
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


class TestCursorHelpers:
    """Tests for cursor encoding/decoding helpers."""

    def test_encode_decode_roundtrip(self):
        from src.apps.backend.routes.inferences_router import _encode_cursor, _decode_cursor
        key = {"inference_id": "abc-123", "created_at": 1700000000000}
        encoded = _encode_cursor(key)
        decoded = _decode_cursor(encoded)
        assert decoded["inference_id"] == "abc-123"
        assert decoded["created_at"] == 1700000000000

    def test_encode_cursor_with_decimal(self):
        from src.apps.backend.routes.inferences_router import _encode_cursor, _decode_cursor
        key = {"inference_id": "x", "created_at": Decimal("1700000000000")}
        encoded = _encode_cursor(key)
        decoded = _decode_cursor(encoded)
        assert decoded["created_at"] == 1700000000000

    def test_decode_cursor_with_padding(self):
        """Cursor decoding handles base64 padding correctly."""
        from src.apps.backend.routes.inferences_router import _encode_cursor, _decode_cursor
        # Test with various key lengths that produce different padding needs
        for i in range(4):
            key = {"inference_id": "x" * (i + 1)}
            encoded = _encode_cursor(key)
            decoded = _decode_cursor(encoded)
            assert decoded["inference_id"] == "x" * (i + 1)


class TestFloatScore:
    """Tests for _float_score helper."""

    def test_float_score_decimal(self):
        from src.apps.backend.routes.inferences_router import _float_score
        assert _float_score(Decimal("0.85")) == pytest.approx(0.85)

    def test_float_score_none_returns_zero(self):
        from src.apps.backend.routes.inferences_router import _float_score
        assert _float_score(None) == 0.0

    def test_float_score_plain_float(self):
        from src.apps.backend.routes.inferences_router import _float_score
        assert _float_score(0.75) == pytest.approx(0.75)

    def test_float_score_integer(self):
        from src.apps.backend.routes.inferences_router import _float_score
        assert _float_score(1) == pytest.approx(1.0)

    def test_float_score_string_number(self):
        from src.apps.backend.routes.inferences_router import _float_score
        assert _float_score("0.5") == pytest.approx(0.5)


class TestNormalizeKeyForJson:
    """Tests for _normalize_key_for_json helper."""

    def test_converts_decimal_to_int(self):
        from src.apps.backend.routes.inferences_router import _normalize_key_for_json
        result = _normalize_key_for_json({"id": "abc", "ts": Decimal("123")})
        assert result == {"id": "abc", "ts": 123}

    def test_leaves_strings_unchanged(self):
        from src.apps.backend.routes.inferences_router import _normalize_key_for_json
        result = _normalize_key_for_json({"id": "abc"})
        assert result == {"id": "abc"}


class TestPresignFailureInList:
    """Tests for presign failure handling in list/get endpoints."""

    @pytest.mark.asyncio
    async def test_list_inferences_presign_failure_returns_empty_url(self, client, auth_headers, dynamodb):
        """List inferences succeeds even when presigning one image fails."""
        _create_inference(dynamodb, "presign-err-1", image_path="s3://bucket/key.jpg")

        with patch(
            "src.apps.backend.routes.inferences_router.presigned_get_url",
            side_effect=Exception("Presign failed"),
        ):
            resp = await client.get("/inferences", headers=auth_headers)
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert len(items) == 1
            assert items[0]["image_url"] == ""

    @pytest.mark.asyncio
    async def test_get_inference_presign_failure_returns_empty_url(self, client, auth_headers, dynamodb):
        """GET /inferences/{id} succeeds even when presigning fails."""
        _create_inference(dynamodb, "presign-get-1", image_path="s3://bucket/key.jpg")

        with patch(
            "src.apps.backend.routes.inferences_router.presigned_get_url",
            side_effect=Exception("Presign failed"),
        ):
            resp = await client.get("/inferences/presign-get-1", headers=auth_headers)
            assert resp.status_code == 200
            assert resp.json()["image_url"] == ""


class TestInferencesWithBadData:
    """Tests for handling malformed DynamoDB data gracefully."""

    @pytest.mark.asyncio
    async def test_non_numeric_prediction_returns_none(self, client, auth_headers, dynamodb):
        """GET /inferences handles non-numeric prediction gracefully."""
        _create_inference(dynamodb, "bad-pred-1", prediction="not-a-number")
        resp = await client.get("/inferences", headers=auth_headers)
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["prediction"] is None

    @pytest.mark.asyncio
    async def test_missing_optional_fields_handled(self, client, auth_headers, dynamodb):
        """GET /inferences handles items with missing optional fields."""
        table = dynamodb.Table("test-inferences")
        table.put_item(Item={
            "inference_id": "minimal-1",
            "user_id": "test-user-1",
            "created_at": int(time.time() * 1000),
            "score": Decimal("0.5"),
            "artist_name": "Artist",
            "artwork_name": "Artwork",
            "image_name": "test.jpg",
            "file_size": 100,
            "image_path": "",
            # No prediction, inference_status, explanation, error_message
        })
        resp = await client.get("/inferences", headers=auth_headers)
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["prediction"] is None
        assert items[0]["inference_status"] is None
        assert items[0]["explanation"] is None


class TestInferencesTableMissing:
    """Tests for missing DDB_INFERENCES_TABLE env var."""

    @pytest.mark.asyncio
    async def test_stats_missing_table_500(self, client, auth_headers, monkeypatch, mock_aws_services):
        """GET /inferences/stats returns 500 if DDB_INFERENCES_TABLE is not set."""
        monkeypatch.delenv("DDB_INFERENCES_TABLE", raising=False)
        resp = await client.get("/inferences/stats", headers=auth_headers)
        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_list_missing_table_500(self, client, auth_headers, monkeypatch, mock_aws_services):
        """GET /inferences returns 500 if DDB_INFERENCES_TABLE is not set."""
        monkeypatch.delenv("DDB_INFERENCES_TABLE", raising=False)
        resp = await client.get("/inferences", headers=auth_headers)
        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_get_missing_table_500(self, client, auth_headers, monkeypatch, mock_aws_services):
        """GET /inferences/{id} returns 500 if DDB_INFERENCES_TABLE is not set."""
        monkeypatch.delenv("DDB_INFERENCES_TABLE", raising=False)
        resp = await client.get("/inferences/some-id", headers=auth_headers)
        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_delete_missing_table_500(self, client, auth_headers, monkeypatch, mock_aws_services):
        """DELETE /inferences/{id} returns 500 if DDB_INFERENCES_TABLE is not set."""
        monkeypatch.delenv("DDB_INFERENCES_TABLE", raising=False)
        resp = await client.delete("/inferences/some-id", headers=auth_headers)
        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_delete_all_missing_table_500(self, client, auth_headers, monkeypatch, mock_aws_services):
        """DELETE /inferences returns 500 if DDB_INFERENCES_TABLE is not set."""
        monkeypatch.delenv("DDB_INFERENCES_TABLE", raising=False)
        resp = await client.delete("/inferences", headers=auth_headers)
        assert resp.status_code == 500


class TestPaginationCursor:
    """Tests for cursor-based pagination."""

    @pytest.mark.asyncio
    async def test_pagination_with_valid_cursor(self, client, auth_headers, dynamodb):
        """Pagination cursor from first page can be used to fetch second page."""
        for i in range(5):
            _create_inference(dynamodb, f"page-inf-{i}", created_at=int(time.time() * 1000) + i)

        # Get first page with limit=2
        resp1 = await client.get("/inferences?limit=2", headers=auth_headers)
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert len(data1["items"]) == 2

        if data1["next_cursor"]:
            # Use cursor to get next page
            cursor = data1["next_cursor"]
            resp2 = await client.get(f"/inferences?limit=2&cursor={cursor}", headers=auth_headers)
            assert resp2.status_code == 200
            data2 = resp2.json()
            assert len(data2["items"]) > 0
            # Items should be different
            ids1 = {item["inference_id"] for item in data1["items"]}
            ids2 = {item["inference_id"] for item in data2["items"]}
            assert ids1.isdisjoint(ids2)

    @pytest.mark.asyncio
    async def test_invalid_cursor_returns_400(self, client, auth_headers):
        """Invalid cursor string returns 400."""
        resp = await client.get("/inferences?cursor=!!!invalid!!!", headers=auth_headers)
        assert resp.status_code == 400
        assert "cursor" in resp.json()["detail"].lower()
