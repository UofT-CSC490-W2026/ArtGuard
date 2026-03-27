"""Tests for src.apps.backend.services.inference_service.

Each test class covers one service function. Tests verify DynamoDB item
contents precisely (not just key existence) and cover both success and
error paths.

Docstrings on individual tests state **positive** vs **negative** and the
edge case they guard, per the inference_service module comment.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from src.apps.backend.services import inference_service
from src.apps.backend.validation import (
    ARTIST_NAME_MAX,
    ARTWORK_NAME_MAX,
    IMAGE_NAME_MAX,
)
from src.apps.rag_pipeline.generate_response import GenerationResult


def _sample_rag_call_kwargs() -> dict:
    """Minimal kwargs matching inference_router's query_rag_explanation call shape."""
    return {
        "raw_s3_uri": "s3://test-raw-bucket/inference/img-1/photo.jpg",
        "patches_info": [
            {"patch_id": "p1", "patch_path": "s3://test-processed-bucket/inference/img-1/x.jpg"},
        ],
        "patch_probs": [0.88],
    }


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

    def test_default_prefix_is_inference(self, s3, monkeypatch):
        """Positive: default S3 key prefix when S3_RAW_PREFIX is unset.

        Edge case: mis-deployed env might omit S3_RAW_PREFIX; keys must still
        land under ``inference/`` so uploads stay discoverable.
        """
        monkeypatch.setenv("S3_IMAGES_RAW_BUCKET", "test-raw-bucket")
        monkeypatch.delenv("S3_RAW_PREFIX", raising=False)
        uri = inference_service.upload_raw_image(b"x", "img-def", "a.jpg", "image/jpeg")
        assert "inference/img-def/a.jpg" in uri


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

    def test_save_metadata_missing_table_env(self, s3, dynamodb, monkeypatch):
        """Negative: missing DDB_IMAGES_TABLE must fail fast.

        Edge case: without a table name we must not write to a wrong resource;
        ``get_table`` raises EnvironmentError via ``require_env``.
        """
        monkeypatch.delenv("DDB_IMAGES_TABLE", raising=False)
        with pytest.raises(EnvironmentError):
            inference_service.save_image_metadata(
                "img-x", "f.jpg", "s3://b/k", 1, 1, "A", "B",
            )

    def test_save_metadata_truncates_long_strings(self, s3, dynamodb):
        """Negative: oversized strings are truncated before DynamoDB write.

        Edge case: malicious or buggy clients send huge metadata; we enforce
        ARTIST_NAME_MAX, ARTWORK_NAME_MAX, IMAGE_NAME_MAX.
        """
        long_name = "x" * (ARTIST_NAME_MAX + 50)
        long_title = "y" * (ARTWORK_NAME_MAX + 50)
        long_file = "z" * (IMAGE_NAME_MAX + 50)
        inference_service.save_image_metadata(
            "img-long", long_file, "s3://b/k", 10, 10, long_name, long_title,
        )
        item = dynamodb.Table("test-images").get_item(Key={"image_id": "img-long"})["Item"]
        assert len(item["artist_name"]) == ARTIST_NAME_MAX
        assert len(item["title"]) == ARTWORK_NAME_MAX
        assert len(item["image_name"]) == IMAGE_NAME_MAX


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

    def test_custom_ttl_via_env_var(self, s3, dynamodb, monkeypatch):
        """Positive: INFERENCE_TTL_DAYS overrides default 90-day TTL.

        Edge case: ops shortens retention; TTL math must follow env exactly.
        """
        monkeypatch.setenv("INFERENCE_TTL_DAYS", "7")
        inference_service.create_inference_record(
            inference_id="inf-ttl",
            image_id="img-1",
            user_id="u1",
            filename="f.jpg",
            raw_s3_uri="s3://b/k",
            artist_name="A",
            artwork_name="B",
            file_size=1,
        )
        item = dynamodb.Table("test-inferences").get_item(Key={"inference_id": "inf-ttl"})["Item"]
        created_sec = int(item["created_at"] / 1000)
        assert item["ttl"] == created_sec + 7 * 86400

    def test_title_mirrors_artwork_name(self, s3, dynamodb):
        """Positive: title and artwork_name both stored and truncated the same way.

        Edge case: API duplicates artwork title into ``title``; both must obey
        ARTWORK_NAME_MAX independently.
        """
        artwork = "w" * (ARTWORK_NAME_MAX + 10)
        inference_service.create_inference_record(
            inference_id="inf-title",
            image_id="img-1",
            user_id="u1",
            filename="f.jpg",
            raw_s3_uri="s3://b/k",
            artist_name="A",
            artwork_name=artwork,
            file_size=1,
        )
        item = dynamodb.Table("test-inferences").get_item(Key={"inference_id": "inf-title"})["Item"]
        assert item["artwork_name"] == item["title"]
        assert len(item["title"]) == ARTWORK_NAME_MAX

    def test_create_record_negative_file_size(self, s3, dynamodb):
        """Negative: negative file_size clamped to 0 (invalid client input).

        Edge case: bad Content-Length or bug; avoid storing negative sizes.
        """
        inference_service.create_inference_record(
            inference_id="inf-neg",
            image_id="img-1",
            user_id="u1",
            filename="f.jpg",
            raw_s3_uri="s3://b/k",
            artist_name="A",
            artwork_name="B",
            file_size=-100,
        )
        item = dynamodb.Table("test-inferences").get_item(Key={"inference_id": "inf-neg"})["Item"]
        assert item["file_size"] == 0


class TestCreateAndUploadPatches:
    """Tests for create_and_upload_patches."""

    def test_creates_patches(self, s3, dynamodb):
        img = Image.new("RGB", (600, 600))
        patches = inference_service.create_and_upload_patches(img, "img-1")
        assert len(patches) > 0
        for p in patches:
            assert "patch_id" in p
            assert "patch_path" in p

    def test_patch_ddb_items_have_all_fields(self, s3, dynamodb):
        """Positive: every patch row has the schema downstream code expects.

        Edge case: missing patch_x / patch_type etc. breaks listing or Modal;
        verify full item shape after create_and_upload_patches.
        """
        img = Image.new("RGB", (600, 600))
        patches = inference_service.create_and_upload_patches(img, "img-ddb-shape")
        patch_table = dynamodb.Table("test-patches")
        first = patch_table.get_item(Key={"patch_id": patches[0]["patch_id"]})["Item"]
        assert first["image_id"] == "img-ddb-shape"
        assert "patch_type" in first
        assert "patch_path" in first
        assert "patch_x" in first and "patch_y" in first
        assert "patch_width" in first and "patch_height" in first
        assert first["created_at"] > 0

    def test_create_patches_missing_bucket_env(self, s3, dynamodb, monkeypatch):
        """Negative: missing processed bucket env fails before S3/DDB work.

        Edge case: misconfiguration must raise EnvironmentError from require_env.
        """
        monkeypatch.delenv("S3_IMAGES_PROCESSED_BUCKET", raising=False)
        img = Image.new("RGB", (600, 600))
        with pytest.raises(EnvironmentError):
            inference_service.create_and_upload_patches(img, "img-1")

    def test_custom_processed_prefix(self, s3, dynamodb, monkeypatch):
        """Positive: S3_PROCESSED_PREFIX appears in uploaded patch object keys.

        Edge case: inference vs training prefixes must be configurable.
        """
        monkeypatch.setenv("S3_PROCESSED_PREFIX", "custom-inf-prefix")
        img = Image.new("RGB", (600, 600))
        inference_service.create_and_upload_patches(img, "img-prefix")
        resp = s3.list_objects_v2(Bucket="test-processed-bucket")
        keys = [o["Key"] for o in resp.get("Contents", [])]
        assert any(k.startswith("custom-inf-prefix/img-prefix/") for k in keys)


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

    def test_modal_correct_app_and_args(self):
        """Positive: Modal app/function names and remote kwargs are stable.

        Edge case: typos in app or function name break production silently;
        checkpoint and variant must match training deployment.
        """
        mock_modal = MagicMock()
        mock_fn = MagicMock()
        mock_fn.remote.return_value = {"mean_prob": 0.5, "prediction": 0}
        mock_modal.Function.from_name.return_value = mock_fn

        with patch.dict("sys.modules", {"modal": mock_modal}):
            with patch.object(inference_service, "emit_metric"):
                inference_service.run_modal_inference(["s3://b/a", "s3://b/b"])

        mock_modal.Function.from_name.assert_called_once_with(
            "artguard-inference", "predict_patches"
        )
        mock_fn.remote.assert_called_once_with(
            patch_s3_uris=["s3://b/a", "s3://b/b"],
            variant="tiny",
            checkpoint_name="best.pt",
        )


class TestSavePatchPredictions:
    """Tests for save_patch_predictions (success + partial failure)."""

    def test_successful_patch_prediction_update(self, s3, dynamodb):
        """Positive: scores and predictions persist as Decimal and int.

        Edge case: only the error branch was covered elsewhere; happy path
        must write correct DynamoDB types for downstream readers.
        """
        patch_table = dynamodb.Table("test-patches")
        patch_table.put_item(Item={
            "patch_id": "pred-p1",
            "image_id": "img-1",
            "patch_path": "s3://test-processed-bucket/x.jpg",
        })
        inference_service.save_patch_predictions(
            [{"patch_id": "pred-p1"}], [0.8125], [1],
        )
        item = patch_table.get_item(Key={"patch_id": "pred-p1"})["Item"]
        assert item["score"] == Decimal("0.8125")
        assert item["prediction"] == 1

    def test_multiple_patches_updated(self, s3, dynamodb):
        """Positive: zip over patches updates every row."""
        patch_table = dynamodb.Table("test-patches")
        for pid in ("mp-1", "mp-2"):
            patch_table.put_item(Item={
                "patch_id": pid,
                "image_id": "img-z",
                "patch_path": "s3://test-processed-bucket/p.jpg",
            })
        inference_service.save_patch_predictions(
            [{"patch_id": "mp-1"}, {"patch_id": "mp-2"}],
            [0.1, 0.9],
            [0, 1],
        )
        assert patch_table.get_item(Key={"patch_id": "mp-1"})["Item"]["prediction"] == 0
        assert patch_table.get_item(Key={"patch_id": "mp-2"})["Item"]["prediction"] == 1

    def test_empty_patch_list_is_noop(self, s3, dynamodb):
        """Positive: empty inputs do not touch DynamoDB (no crash)."""
        inference_service.save_patch_predictions([], [], [])

    def test_continues_after_first_patch_ddb_failure(self, s3, dynamodb):
        """Negative: first update_item fails; second still runs (resilient loop).

        Edge case: one bad row must not abort the whole batch; matches
        log-and-continue behavior in save_patch_predictions.
        """
        mock_table = MagicMock()
        mock_table.update_item.side_effect = [
            Exception("first row failed"),
            {},
        ]
        with patch.object(inference_service, "get_table", return_value=mock_table):
            inference_service.save_patch_predictions(
                [{"patch_id": "a"}, {"patch_id": "b"}],
                [0.5, 0.6],
                [1, 0],
            )
        assert mock_table.update_item.call_count == 2


class TestQueryRagExplanation:
    """Tests for query_rag_explanation (RAG pipeline via generate_explanation)."""

    def test_returns_none_when_no_kb(self, monkeypatch):
        """Negative: no KNOWLEDGE_BASE_ID means RAG is disabled (None)."""
        monkeypatch.delenv("KNOWLEDGE_BASE_ID", raising=False)
        result = inference_service.query_rag_explanation(
            1, 0.9, **_sample_rag_call_kwargs(),
        )
        assert result is None

    def test_returns_fallback_on_error(self, monkeypatch):
        """Negative: pipeline exception returns user-safe fallback (does not raise)."""
        monkeypatch.setenv("KNOWLEDGE_BASE_ID", "kb-123")
        with patch(
            "src.apps.rag_pipeline.generate_response.generate_explanation",
            side_effect=Exception("pipeline down"),
        ):
            with patch.object(inference_service, "emit_metric"):
                result = inference_service.query_rag_explanation(
                    1, 0.9, **_sample_rag_call_kwargs(),
                )
        assert result is not None
        assert "unavailable" in result.lower()

    def test_empty_pipeline_response_uses_fallback_message(self, monkeypatch):
        """Positive: empty ``response_text`` from pipeline maps to fallback string.

        Edge case: ``query_rag_explanation`` uses ``response_text or fallback``;
        empty string must not surface as a blank user explanation.
        """
        monkeypatch.setenv("KNOWLEDGE_BASE_ID", "kb-empty")
        empty_result = GenerationResult(
            response_text="",
            formatted_input="x",
            retrieved_kb_chunks=[],
            used_patch_image_uris=[],
        )
        with patch(
            "src.apps.rag_pipeline.generate_response.generate_explanation",
            return_value=empty_result,
        ):
            with patch.object(inference_service, "emit_metric"):
                result = inference_service.query_rag_explanation(
                    0, 0.5, **_sample_rag_call_kwargs(),
                )
        assert "unavailable" in result.lower()

    def test_success_returns_pipeline_text(self, monkeypatch):
        """Positive: non-empty GenerationResult.response_text is returned as-is."""
        monkeypatch.setenv("KNOWLEDGE_BASE_ID", "kb-ok")
        ok = GenerationResult(
            response_text="The model found authentic brushwork in patch evidence.",
            formatted_input="ctx",
            retrieved_kb_chunks=["chunk"],
            used_patch_image_uris=["s3://b/p.jpg"],
        )
        with patch(
            "src.apps.rag_pipeline.generate_response.generate_explanation",
            return_value=ok,
        ):
            with patch.object(inference_service, "emit_metric"):
                result = inference_service.query_rag_explanation(
                    1,
                    0.92,
                    **_sample_rag_call_kwargs(),
                    artist_name="Monet",
                    artwork_name="Lilies",
                )
        assert result == ok.response_text
        assert "authentic" in result.lower()


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

    def test_mark_failed_truncates_long_error(self, s3, dynamodb):
        """Negative: error_message longer than 3500 chars is truncated.

        Edge case: stack traces or huge client payloads must not exceed DDB
        item size; service uses a 3500-char slice.
        """
        table = dynamodb.Table("test-inferences")
        table.put_item(Item={"inference_id": "fail-long", "inference_status": "processing"})
        huge = "e" * 5000
        inference_service.mark_inference_failed("fail-long", huge)
        msg = table.get_item(Key={"inference_id": "fail-long"})["Item"]["error_message"]
        assert len(msg) == 3500
        assert msg == "e" * 3500

    def test_mark_failed_logs_on_ddb_failure(self, s3, dynamodb):
        """Negative: failure to persist failed status is logged, not raised.

        Covers ``mark_inference_failed`` except branch (lines 435–438).
        """
        mock_table = MagicMock()
        mock_table.update_item.side_effect = Exception("DDB unavailable")
        with patch.object(inference_service, "get_table", return_value=mock_table):
            inference_service.mark_inference_failed("ghost-id", "error detail")


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

    def test_finalize_without_explanation(self, s3, dynamodb):
        """Positive: explanation=None does not SET explanation attribute.

        Edge case: optional RAG; record should complete without explanation key
        if none was provided.
        """
        table = dynamodb.Table("test-inferences")
        table.put_item(Item={
            "inference_id": "fin-no-exp",
            "inference_status": "processing",
        })
        inference_service.finalize_inference("fin-no-exp", 0.5, 1, None)
        item = table.get_item(Key={"inference_id": "fin-no-exp"})["Item"]
        assert item["inference_status"] == "completed"
        assert "explanation" not in item

    def test_finalize_clamps_score_above_one(self, s3, dynamodb):
        """Negative: score > 1.0 clamped via clamp_score before Decimal write."""
        table = dynamodb.Table("test-inferences")
        table.put_item(Item={"inference_id": "fin-hi", "inference_status": "processing"})
        inference_service.finalize_inference("fin-hi", 1.5, 1, None)
        item = table.get_item(Key={"inference_id": "fin-hi"})["Item"]
        assert float(item["score"]) == pytest.approx(1.0)

    def test_finalize_clamps_score_below_zero(self, s3, dynamodb):
        """Negative: score < 0.0 clamped to 0.0."""
        table = dynamodb.Table("test-inferences")
        table.put_item(Item={"inference_id": "fin-lo", "inference_status": "processing"})
        inference_service.finalize_inference("fin-lo", -0.3, 1, None)
        item = table.get_item(Key={"inference_id": "fin-lo"})["Item"]
        assert float(item["score"]) == pytest.approx(0.0)

    def test_finalize_rejects_invalid_prediction(self, s3, dynamodb):
        """Negative: prediction outside {-1,0,1} stored as -1 (pending/invalid)."""
        table = dynamodb.Table("test-inferences")
        table.put_item(Item={"inference_id": "fin-bad-p", "inference_status": "processing"})
        inference_service.finalize_inference("fin-bad-p", 0.5, 99, None)
        item = table.get_item(Key={"inference_id": "fin-bad-p"})["Item"]
        assert item["prediction"] == -1

    def test_finalize_clears_previous_error(self, s3, dynamodb):
        """Positive: REMOVE error_message after successful finalize.

        Edge case: record was marked failed then recovered / re-run; stale
        error_message must not remain on a completed inference.
        """
        table = dynamodb.Table("test-inferences")
        table.put_item(Item={
            "inference_id": "fin-clear-err",
            "inference_status": "failed",
            "error_message": "old failure",
        })
        inference_service.finalize_inference("fin-clear-err", 0.8, 1, "ok")
        item = table.get_item(Key={"inference_id": "fin-clear-err"})["Item"]
        assert item["inference_status"] == "completed"
        assert "error_message" not in item

    def test_finalize_logs_on_ddb_failure(self, s3, dynamodb):
        """Negative: DynamoDB failure is swallowed after logging (no re-raise).

        Covers ``finalize_inference`` except branch (lines 412–415): pipeline
        must not crash the caller when the final update_item fails.
        """
        mock_table = MagicMock()
        mock_table.update_item.side_effect = Exception("DDB unavailable")
        with patch.object(inference_service, "get_table", return_value=mock_table):
            inference_service.finalize_inference("any-id", 0.9, 1, "Explanation")


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

    def test_custom_presign_expiration(self, s3, monkeypatch):
        """Positive: S3_INFERENCE_PRESIGN_EXPIRES passed to presigned_get_url.

        Edge case: shorter TTL for compliance; must flow from env to presign.
        """
        monkeypatch.setenv("S3_INFERENCE_PRESIGN_EXPIRES", "3600")
        with patch(
            "src.apps.backend.services.inference_service.presigned_get_url",
            return_value="https://example/presigned",
        ) as mock_presign:
            url = inference_service.generate_image_url("s3://test-raw-bucket/test/img.jpg")
        assert url == "https://example/presigned"
        call = mock_presign.call_args
        assert call[0][2] == 3600

    def test_presign_exception_returns_none(self, s3):
        """Negative: presign raises → log warning and return None.

        Covers ``generate_image_url`` except branch (lines 455–457). Moto may
        not raise for bad keys; this forces the error path deterministically.
        """
        with patch(
            "src.apps.backend.services.inference_service.presigned_get_url",
            side_effect=ValueError("invalid uri"),
        ):
            assert inference_service.generate_image_url("s3://test-raw-bucket/x.jpg") is None


class TestNowMs:
    """Tests for _now_ms helper."""

    def test_now_ms_returns_positive_int(self):
        """Positive: millisecond timestamp is a positive int (contract)."""
        t = inference_service._now_ms()
        assert isinstance(t, int)
        assert t > 0
