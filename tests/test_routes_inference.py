"""Tests for POST /inference route handler.

Covers the full inference pipeline: authentication, input validation
(empty files, invalid images, oversized uploads, blank metadata),
the happy path through Modal + RAG, and error handling when
downstream services fail.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest


class TestInferenceEndpoint:
    """Tests for POST /inference."""

    @pytest.mark.asyncio
    async def test_no_auth_401(self, client):
        """Unauthenticated requests are rejected before any processing."""
        resp = await client.post("/inference")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_file_400(self, client, auth_headers):
        """A zero-byte upload is caught before image parsing."""
        resp = await client.post(
            "/inference",
            data={"artist_name": "Monet", "artwork_name": "Lilies"},
            files={"file": ("empty.jpg", b"", "image/jpeg")},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_invalid_image_400(self, client, auth_headers):
        """Non-image bytes with an image extension are rejected by PIL."""
        resp = await client.post(
            "/inference",
            data={"artist_name": "Monet", "artwork_name": "Lilies"},
            files={"file": ("bad.jpg", b"not-an-image", "image/jpeg")},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "not a valid image" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_oversized_file_400(self, client, auth_headers):
        """Files exceeding MAX_UPLOAD_SIZE_BYTES (5 MB) are rejected."""
        # Create a 6 MB payload — larger than the 5 MB limit
        oversized = b"x" * (6 * 1024 * 1024)
        resp = await client.post(
            "/inference",
            data={"artist_name": "Monet", "artwork_name": "Lilies"},
            files={"file": ("huge.jpg", oversized, "image/jpeg")},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "too large" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_blank_artist_400(self, client, auth_headers, sample_image_bytes):
        """Whitespace-only artist_name is treated as empty after strip()."""
        resp = await client.post(
            "/inference",
            data={"artist_name": "  ", "artwork_name": "Lilies"},
            files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "required" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_blank_artwork_400(self, client, auth_headers, sample_image_bytes):
        """Whitespace-only artwork_name is also rejected."""
        resp = await client.post(
            "/inference",
            data={"artist_name": "Monet", "artwork_name": "   "},
            files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "required" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_successful_inference(self, client, auth_headers, sample_image_bytes, s3, dynamodb):
        """Happy path: image is processed, Modal returns a prediction, RAG adds an explanation."""
        mock_result = {
            "mean_prob": 0.87,
            "prediction": 1,
            "patch_probs": [0.9, 0.85, 0.86, 0.88],
            "patch_preds": [1, 1, 1, 1],
        }

        with patch("src.apps.backend.services.inference_service.run_modal_inference", return_value=mock_result):
            with patch("src.apps.backend.services.inference_service.query_rag_explanation", return_value="Looks authentic."):
                resp = await client.post(
                    "/inference",
                    data={"artist_name": "Monet", "artwork_name": "Water Lilies"},
                    files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
                    headers=auth_headers,
                )
                assert resp.status_code == 200
                data = resp.json()

                # Verify all response fields are present and correct
                assert data["prediction"] == 1
                assert data["score"] == pytest.approx(0.87)
                assert data["explanation"] == "Looks authentic."

                # inference_id should be a valid UUID
                uuid.UUID(data["inference_id"])  # raises ValueError if invalid

                # image_url should be a presigned S3 URL (or None in test)
                assert "image_url" in data

    @pytest.mark.asyncio
    async def test_successful_inference_forgery(self, client, auth_headers, sample_image_bytes, s3, dynamodb):
        """Verify prediction=0 (forgery) is returned correctly."""
        mock_result = {
            "mean_prob": 0.2,
            "prediction": 0,
            "patch_probs": [0.1, 0.3],
            "patch_preds": [0, 0],
        }
        with patch("src.apps.backend.services.inference_service.run_modal_inference", return_value=mock_result):
            with patch("src.apps.backend.services.inference_service.query_rag_explanation", return_value="Potential forgery."):
                resp = await client.post(
                    "/inference",
                    data={"artist_name": "Unknown", "artwork_name": "Suspicious"},
                    files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
                    headers=auth_headers,
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["prediction"] == 0
                assert data["score"] == pytest.approx(0.2)

    @pytest.mark.asyncio
    async def test_special_characters_in_metadata(self, client, auth_headers, sample_image_bytes, s3, dynamodb):
        """Artist/artwork names with special chars don't cause injection or crashes."""
        mock_result = {"mean_prob": 0.5, "prediction": 0, "patch_probs": [0.5], "patch_preds": [0]}
        with patch("src.apps.backend.services.inference_service.run_modal_inference", return_value=mock_result):
            with patch("src.apps.backend.services.inference_service.query_rag_explanation", return_value=None):
                resp = await client.post(
                    "/inference",
                    data={
                        "artist_name": "O'Keeffe <script>alert(1)</script>",
                        "artwork_name": 'Jimson "Weed" & Sunset; DROP TABLE--',
                    },
                    files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
                    headers=auth_headers,
                )
                # Should succeed — special chars are stored as plain text, not interpreted
                assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_modal_failure_500(self, client, auth_headers, sample_image_bytes, s3, dynamodb):
        """When Modal is down, the user gets a clear 500 with 'temporarily unavailable'."""
        with patch(
            "src.apps.backend.services.inference_service.run_modal_inference",
            side_effect=RuntimeError("Model down"),
        ):
            resp = await client.post(
                "/inference",
                data={"artist_name": "Monet", "artwork_name": "Lilies"},
                files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
                headers=auth_headers,
            )
            assert resp.status_code == 500
            assert "temporarily unavailable" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_config_error_500(self, client, auth_headers, sample_image_bytes, monkeypatch, mock_aws_services):
        """Missing S3 bucket config returns a server configuration error, not a crash."""
        monkeypatch.delenv("S3_IMAGES_RAW_BUCKET", raising=False)
        resp = await client.post(
            "/inference",
            data={"artist_name": "Monet", "artwork_name": "Lilies"},
            files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
            headers=auth_headers,
        )
        assert resp.status_code == 500
        assert "configuration" in resp.json()["detail"].lower()
