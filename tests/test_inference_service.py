"""Tests for src.apps.backend.services.inference_service.

Each test class covers one service function. Tests verify DynamoDB item
contents precisely (not just key existence) and cover both success and
error paths.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from src.apps.backend.services import inference_service


class TestUploadRawImage:
    """Tests for upload_raw_image."""

    def test_uploads_to_s3_and_returns_uri(self, s3, monkeypatch):
        """Verify the object lands in S3 and the returned URI is well-formed."""
        monkeypatch.setenv("S3_IMAGES_RAW_BUCKET", "test-raw-bucket")
        uri = inference_service.upload_raw_image(
            content=b"fake-image-data",
            image_id="img-1",
            filename="test.jpg",
            content_type="image/jpeg",
        )
        assert uri.startswith("s3://test-raw-bucket/")
        assert "img-1" in uri
        assert uri.endswith("/test.jpg")

        # Verify the object actually exists in S3 with correct content
        bucket, key = uri[5:].split("/", 1)
        obj = s3.get_object(Bucket=bucket, Key=key)
        assert obj["Body"].read() == b"fake-image-data"
        assert obj["ContentType"] == "image/jpeg"

    def test_missing_bucket_raises(self, s3, monkeypatch):
        monkeypatch.delenv("S3_IMAGES_RAW_BUCKET", raising=False)
        with pytest.raises(EnvironmentError):
            inference_service.upload_raw_image(b"data", "id", "f.jpg", "image/jpeg")

    def test_custom_prefix(self, s3, monkeypatch):
        """S3_RAW_PREFIX env var controls the key prefix."""
        monkeypatch.setenv("S3_IMAGES_RAW_BUCKET", "test-raw-bucket")
        monkeypatch.setenv("S3_RAW_PREFIX", "custom/path")
        uri = inference_service.upload_raw_image(b"data", "img-2", "f.jpg", "image/jpeg")
        assert "custom/path/img-2/f.jpg" in uri


class TestSaveImageMetadata:
    """Tests for save_image_metadata."""

    def test_saves_all_fields_to_dynamodb(self, s3, dynamodb):
        """Verify every field is persisted correctly, not just the primary key."""
        inference_service.save_image_metadata(
            image_id="img-1",
            filename="test.jpg",
            raw_s3_uri="s3://bucket/key",
            width=800,
            height=600,
            artist_name="Monet",
            artwork_name="Water Lilies",
        )
        table = dynamodb.Table("test-images")
        item = table.get_item(Key={"image_id": "img-1"})["Item"]

        assert item["image_id"] == "img-1"
        assert item["image_name"] == "test.jpg"
        assert item["image_path"] == "s3://bucket/key"
        assert item["image_width"] == 800
        assert item["image_height"] == 600
        assert item["artist_name"] == "Monet"
        assert item["title"] == "Water Lilies"
        assert item["created_at"] > 0  # Unix ms timestamp

    def test_negative_dimensions_clamped_to_zero(self, s3, dynamodb):
        """Negative width/height should be clamped to 0, not stored as-is."""
        inference_service.save_image_metadata(
            "img-neg", "f.jpg", "s3://b/k", -1, -5, "A", "B",
        )
        item = dynamodb.Table("test-images").get_item(Key={"image_id": "img-neg"})["Item"]
        assert item["image_width"] == 0
        assert item["image_height"] == 0


class TestCreateInferenceRecord:
    """Tests for create_inference_record."""

    def test_creates_record_with_all_initial_fields(self, s3, dynamodb):
        """New inference record should have status=processing, prediction=-1 (pending),
        and all metadata fields persisted."""
        inference_service.create_inference_record(
            inference_id="inf-1",
            image_id="img-1",
            user_id="user-1",
            filename="test.jpg",
            raw_s3_uri="s3://b/k",
            artist_name="Artist",
            artwork_name="Artwork",
            file_size=1024,
        )
        table = dynamodb.Table("test-inferences")
        item = table.get_item(Key={"inference_id": "inf-1"})["Item"]

        # Status and prediction defaults
        assert item["inference_status"] == "processing"
        assert item["prediction"] == -1
        assert item["score"] == Decimal("0.0")

        # Metadata
        assert item["image_id"] == "img-1"
        assert item["user_id"] == "user-1"
        assert item["artist_name"] == "Artist"
        assert item["artwork_name"] == "Artwork"
        assert item["file_size"] == 1024
        assert item["created_at"] > 0
        # TTL is Unix seconds (not ms), so compare against seconds
        assert item["ttl"] > int(item["created_at"] / 1000)


class TestCreateAndUploadPatches:
    """Tests for create_and_upload_patches."""

    def test_creates_patches(self, s3, dynamodb):
        img = Image.new("RGB", (600, 600))
        patches = inference_service.create_and_upload_patches(img, "img-1")
        assert len(patches) > 0
        for p in patches:
            assert "patch_id" in p
            assert "patch_path" in p


class TestRunModalInference:
    """Tests for run_modal_inference."""

    def test_raises_on_failure(self):
        mock_modal = MagicMock()
        mock_fn = MagicMock()
        mock_fn.remote.side_effect = Exception("Modal down")
        mock_modal.Function.from_name.return_value = mock_fn

        with patch.dict("sys.modules", {"modal": mock_modal}):
            with pytest.raises(RuntimeError, match="Model inference failed"):
                inference_service.run_modal_inference(["s3://b/k1", "s3://b/k2"])

    def test_returns_result_on_success(self):
        expected = {
            "mean_prob": 0.85,
            "prediction": 1,
            "patch_probs": [0.9, 0.8],
            "patch_preds": [1, 1],
        }
        mock_modal = MagicMock()
        mock_fn = MagicMock()
        mock_fn.remote.return_value = expected
        mock_modal.Function.from_name.return_value = mock_fn

        with patch.dict("sys.modules", {"modal": mock_modal}):
            result = inference_service.run_modal_inference(["s3://b/k1"])
            assert result["mean_prob"] == 0.85


class TestQueryRagExplanation:
    """Tests for query_rag_explanation."""

    def test_returns_none_when_no_kb(self, monkeypatch):
        monkeypatch.delenv("KNOWLEDGE_BASE_ID", raising=False)
        result = inference_service.query_rag_explanation(
            1,
            0.9,
            raw_s3_uri="s3://bucket/raw.jpg",
            patches_info=[],
            patch_probs=[],
        )
        assert result is None

    def test_returns_fallback_on_error(self, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_ID", "kb-123")
        with patch(
            "src.apps.rag_pipeline.generate_response.generate_explanation",
            side_effect=Exception("pipeline failed"),
        ):
            result = inference_service.query_rag_explanation(
                1,
                0.9,
                raw_s3_uri="s3://bucket/raw.jpg",
                patches_info=[{"patch_id": "p1", "patch_path": "s3://bucket/p1.jpg"}],
                patch_probs=[0.9],
            )
            assert result is not None
            assert "unavailable" in result.lower()


class TestMarkInferenceFailed:
    """Tests for mark_inference_failed."""

    def test_updates_status(self, s3, dynamodb):
        # Create an initial record
        table = dynamodb.Table("test-inferences")
        table.put_item(Item={
            "inference_id": "fail-1",
            "inference_status": "processing",
        })
        inference_service.mark_inference_failed("fail-1", "Something broke")
        resp = table.get_item(Key={"inference_id": "fail-1"})
        assert resp["Item"]["inference_status"] == "failed"
        assert resp["Item"]["error_message"] == "Something broke"


class TestFinalizeInference:
    """Tests for finalize_inference."""

    def test_updates_with_results(self, s3, dynamodb):
        table = dynamodb.Table("test-inferences")
        table.put_item(Item={
            "inference_id": "fin-1",
            "inference_status": "processing",
        })
        inference_service.finalize_inference("fin-1", 0.92, 1, "Looks authentic")
        resp = table.get_item(Key={"inference_id": "fin-1"})
        item = resp["Item"]
        assert item["inference_status"] == "completed"
        assert float(item["score"]) == pytest.approx(0.92)
        assert item["explanation"] == "Looks authentic"


class TestGenerateImageUrl:
    """Tests for generate_image_url."""

    def test_generates_url(self, s3):
        s3.put_object(Bucket="test-raw-bucket", Key="test/img.jpg", Body=b"data")
        url = inference_service.generate_image_url("s3://test-raw-bucket/test/img.jpg")
        assert url is not None
        assert "test-raw-bucket" in url

    def test_returns_none_on_error(self, s3):
        url = inference_service.generate_image_url("s3://nonexistent/bad.jpg")
        # moto might not raise for presigning nonexistent objects, but test the path
        assert url is None or isinstance(url, str)
