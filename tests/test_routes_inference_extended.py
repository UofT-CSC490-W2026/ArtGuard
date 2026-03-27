"""Extended tests for POST /inference route covering additional edge cases.

Covers:
- Generic exception during pipeline prep (non-EnvironmentError)
- Patch data in response
- Image dimensions in response
- No RAG explanation (None)
- Long artist/artwork names (truncation)
- Various image formats
"""

import io
from unittest.mock import patch

import pytest
from PIL import Image


def _make_image_bytes(width=600, height=600, fmt="JPEG") -> bytes:
    """Create minimal valid image bytes."""
    img = Image.new("RGB", (width, height), color="blue")
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


class TestInferenceRouteExtended:
    """Extended tests for POST /inference."""

    @pytest.mark.asyncio
    async def test_generic_pipeline_error_500(self, client, auth_headers, sample_image_bytes, s3, dynamodb):
        """A non-EnvironmentError exception during patch creation returns 500."""
        with patch(
            "src.apps.backend.routes.inference_router.inference_service.create_and_upload_patches",
            side_effect=RuntimeError("Unexpected PIL error"),
        ):
            resp = await client.post(
                "/inference",
                data={"artist_name": "Monet", "artwork_name": "Lilies"},
                files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
                headers=auth_headers,
            )
            assert resp.status_code == 500
            assert "failed to process" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_response_includes_patch_data(self, client, auth_headers, sample_image_bytes, s3, dynamodb):
        """Successful inference response includes patch_data array."""
        mock_result = {
            "mean_prob": 0.87,
            "prediction": 1,
            "patch_probs": [0.9, 0.85, 0.86, 0.88],
            "patch_preds": [1, 1, 1, 1],
        }
        with patch("src.apps.backend.services.inference_service.run_modal_inference", return_value=mock_result):
            with patch("src.apps.backend.services.inference_service.query_rag_explanation", return_value=None):
                resp = await client.post(
                    "/inference",
                    data={"artist_name": "Monet", "artwork_name": "Water Lilies"},
                    files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
                    headers=auth_headers,
                )
                assert resp.status_code == 200
                data = resp.json()
                assert "patch_data" in data
                assert isinstance(data["patch_data"], list)
                assert len(data["patch_data"]) > 0
                # Each patch should have x, y, w, h, prob
                for patch_item in data["patch_data"]:
                    assert "x" in patch_item
                    assert "y" in patch_item
                    assert "w" in patch_item
                    assert "h" in patch_item
                    assert "prob" in patch_item

    @pytest.mark.asyncio
    async def test_response_includes_image_dimensions(self, client, auth_headers, sample_image_bytes, s3, dynamodb):
        """Successful inference response includes image_width and image_height."""
        mock_result = {
            "mean_prob": 0.5,
            "prediction": 0,
            "patch_probs": [0.5],
            "patch_preds": [0],
        }
        with patch("src.apps.backend.services.inference_service.run_modal_inference", return_value=mock_result):
            with patch("src.apps.backend.services.inference_service.query_rag_explanation", return_value=None):
                resp = await client.post(
                    "/inference",
                    data={"artist_name": "Artist", "artwork_name": "Artwork"},
                    files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
                    headers=auth_headers,
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["image_width"] > 0
                assert data["image_height"] > 0

    @pytest.mark.asyncio
    async def test_no_rag_explanation_returns_none(self, client, auth_headers, sample_image_bytes, s3, dynamodb):
        """When RAG returns None, explanation field is None in response."""
        mock_result = {
            "mean_prob": 0.7,
            "prediction": 1,
            "patch_probs": [0.7],
            "patch_preds": [1],
        }
        with patch("src.apps.backend.services.inference_service.run_modal_inference", return_value=mock_result):
            with patch("src.apps.backend.services.inference_service.query_rag_explanation", return_value=None):
                resp = await client.post(
                    "/inference",
                    data={"artist_name": "Artist", "artwork_name": "Artwork"},
                    files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
                    headers=auth_headers,
                )
                assert resp.status_code == 200
                assert resp.json()["explanation"] is None

    @pytest.mark.asyncio
    async def test_long_artist_name_truncated(self, client, auth_headers, sample_image_bytes, s3, dynamodb):
        """Artist name longer than ARTIST_NAME_MAX is truncated, not rejected."""
        mock_result = {
            "mean_prob": 0.5,
            "prediction": 0,
            "patch_probs": [0.5],
            "patch_preds": [0],
        }
        long_name = "A" * 300  # Over ARTIST_NAME_MAX=200
        with patch("src.apps.backend.services.inference_service.run_modal_inference", return_value=mock_result):
            with patch("src.apps.backend.services.inference_service.query_rag_explanation", return_value=None):
                resp = await client.post(
                    "/inference",
                    data={"artist_name": long_name, "artwork_name": "Artwork"},
                    files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
                    headers=auth_headers,
                )
                assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_png_image_accepted(self, client, auth_headers, s3, dynamodb):
        """PNG images are accepted and processed correctly."""
        png_bytes = _make_image_bytes(fmt="PNG")
        mock_result = {
            "mean_prob": 0.6,
            "prediction": 1,
            "patch_probs": [0.6],
            "patch_preds": [1],
        }
        with patch("src.apps.backend.services.inference_service.run_modal_inference", return_value=mock_result):
            with patch("src.apps.backend.services.inference_service.query_rag_explanation", return_value=None):
                resp = await client.post(
                    "/inference",
                    data={"artist_name": "Artist", "artwork_name": "Artwork"},
                    files={"file": ("test.png", png_bytes, "image/png")},
                    headers=auth_headers,
                )
                assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_inference_id_is_valid_uuid(self, client, auth_headers, sample_image_bytes, s3, dynamodb):
        """inference_id in response is a valid UUID."""
        import uuid
        mock_result = {
            "mean_prob": 0.5,
            "prediction": 0,
            "patch_probs": [0.5],
            "patch_preds": [0],
        }
        with patch("src.apps.backend.services.inference_service.run_modal_inference", return_value=mock_result):
            with patch("src.apps.backend.services.inference_service.query_rag_explanation", return_value=None):
                resp = await client.post(
                    "/inference",
                    data={"artist_name": "Artist", "artwork_name": "Artwork"},
                    files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
                    headers=auth_headers,
                )
                assert resp.status_code == 200
                # Should not raise ValueError
                uuid.UUID(resp.json()["inference_id"])

    @pytest.mark.asyncio
    async def test_upload_prep_environment_error_500(self, client, auth_headers, sample_image_bytes, monkeypatch, mock_aws_services):
        """EnvironmentError during upload prep returns 500 with configuration error."""
        monkeypatch.delenv("S3_IMAGES_RAW_BUCKET", raising=False)
        resp = await client.post(
            "/inference",
            data={"artist_name": "Monet", "artwork_name": "Lilies"},
            files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
            headers=auth_headers,
        )
        assert resp.status_code == 500
        assert "configuration" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_no_auth_returns_401(self, client):
        """POST /inference without auth returns 401."""
        resp = await client.post("/inference")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_file_returns_400(self, client, auth_headers):
        """Empty file upload returns 400."""
        resp = await client.post(
            "/inference",
            data={"artist_name": "Monet", "artwork_name": "Lilies"},
            files={"file": ("empty.jpg", b"", "image/jpeg")},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_invalid_image_bytes_returns_400(self, client, auth_headers):
        """Non-image bytes return 400."""
        resp = await client.post(
            "/inference",
            data={"artist_name": "Monet", "artwork_name": "Lilies"},
            files={"file": ("bad.jpg", b"not-an-image", "image/jpeg")},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "not a valid image" in resp.json()["detail"].lower()
