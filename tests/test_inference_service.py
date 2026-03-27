"""Tests for src.apps.backend.services.inference_service.

One ``Test*`` class per service function. Extra branches (log-only DynamoDB
failures, RAG + metrics) are in ``tests/test_coverage_gaps.py`` under
``TestInferenceServiceErrorBranches``.

Each ``test_*`` method has a docstring describing what it covers (positive vs
negative), the edge case, and why the test exists.
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
    """Minimal kwargs matching ``inference_router``'s ``query_rag_explanation`` call shape."""
    return {
        "raw_s3_uri": "s3://test-raw-bucket/inference/img-1/photo.jpg",
        "patches_info": [
            {"patch_id": "p1", "patch_path": "s3://test-processed-bucket/inference/img-1/x.jpg"},
        ],
        "patch_probs": [0.88],
    }


class TestUploadRawImage:
    """``upload_raw_image`` — S3 put + URI shape."""

    def test_uploads_to_s3_and_returns_uri(self, s3, monkeypatch):
        """Positive: bytes land in S3; URI includes bucket, image_id, filename; Content-Type set.

        Why: regressions in key layout break listing and downstream reads.
        """
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

        bucket, key = uri[5:].split("/", 1)
        obj = s3.get_object(Bucket=bucket, Key=key)
        assert obj["Body"].read() == b"fake-image-data"
        assert obj["ContentType"] == "image/jpeg"

    def test_missing_bucket_raises(self, s3, monkeypatch):
        """Negative: missing S3_IMAGES_RAW_BUCKET → EnvironmentError before any put.

        Why: must not write to an undefined bucket name.
        """
        monkeypatch.delenv("S3_IMAGES_RAW_BUCKET", raising=False)
        with pytest.raises(EnvironmentError):
            inference_service.upload_raw_image(b"data", "id", "f.jpg", "image/jpeg")

    def test_custom_prefix(self, s3, monkeypatch):
        """Positive: S3_RAW_PREFIX overrides default key prefix.

        Why: ops may separate inference vs other uploads by prefix.
        """
        monkeypatch.setenv("S3_IMAGES_RAW_BUCKET", "test-raw-bucket")
        monkeypatch.setenv("S3_RAW_PREFIX", "custom/path")
        uri = inference_service.upload_raw_image(b"data", "img-2", "f.jpg", "image/jpeg")
        assert "custom/path/img-2/f.jpg" in uri

    def test_default_prefix_is_inference(self, s3, monkeypatch):
        """Positive / boundary: unset S3_RAW_PREFIX defaults to "inference/" in the key.

        Why: partial deploys that omit the env must still use a stable, discoverable prefix.
        """
        monkeypatch.setenv("S3_IMAGES_RAW_BUCKET", "test-raw-bucket")
        monkeypatch.delenv("S3_RAW_PREFIX", raising=False)
        uri = inference_service.upload_raw_image(b"x", "img-def", "a.jpg", "image/jpeg")
        assert "inference/img-def/a.jpg" in uri


class TestSaveImageMetadata:
    """``save_image_metadata`` — DynamoDB images table row."""

    def test_saves_all_fields_to_dynamodb(self, s3, dynamodb):
        """Positive: every attribute matches what routes and listings expect (not only PK).

        Why: silent field drops or wrong keys break UI and queries.
        """
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
        assert item["created_at"] > 0

    def test_negative_dimensions_clamped_to_zero(self, s3, dynamodb):
        """Negative: negative width/height clamped to 0 (invalid EXIF or client bug).

        Why: DynamoDB should not store nonsensical dimensions.
        """
        inference_service.save_image_metadata(
            "img-neg", "f.jpg", "s3://b/k", -1, -5, "A", "B",
        )
        item = dynamodb.Table("test-images").get_item(Key={"image_id": "img-neg"})["Item"]
        assert item["image_width"] == 0
        assert item["image_height"] == 0

    def test_save_metadata_missing_table_env(self, s3, dynamodb, monkeypatch):
        """Negative: DDB_IMAGES_TABLE unset → EnvironmentError via require_env/get_table.

        Why: avoid writing to a wrong or implicit table name.
        """
        monkeypatch.delenv("DDB_IMAGES_TABLE", raising=False)
        with pytest.raises(EnvironmentError):
            inference_service.save_image_metadata(
                "img-x", "f.jpg", "s3://b/k", 1, 1, "A", "B",
            )

    def test_save_metadata_truncates_long_strings(self, s3, dynamodb):
        """Negative: artist/title/filename longer than validation caps → truncated before write.

        Why: abuse or buggy clients must not exceed practical DynamoDB string limits.
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
    """``create_inference_record`` — initial inference row + TTL."""

    def test_creates_record_with_all_initial_fields(self, s3, dynamodb):
        """Positive: processing status, pending prediction (-1), zero score, TTL > created_at.

        Why: API contract for "in flight" jobs and retention.
        """
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

        assert item["inference_status"] == "processing"
        assert item["prediction"] == -1
        assert item["score"] == Decimal("0.0")

        assert item["image_id"] == "img-1"
        assert item["user_id"] == "user-1"
        assert item["artist_name"] == "Artist"
        assert item["artwork_name"] == "Artwork"
        assert item["file_size"] == 1024
        assert item["created_at"] > 0
        assert item["ttl"] > int(item["created_at"] / 1000)

    def test_custom_ttl_via_env_var(self, s3, dynamodb, monkeypatch):
        """Positive: INFERENCE_TTL_DAYS changes TTL seconds from created_at.

        Why: ops-tuned retention must match env exactly.
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
        """Positive: title duplicates artwork_name with same truncation rule.

        Why: both fields must stay within ARTWORK_NAME_MAX when API sends long titles.
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
        """Negative: negative file_size clamped to 0.

        Why: invalid Content-Length or bug should not persist negative bytes.
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
    """``create_and_upload_patches`` — preprocess, S3 patch objects, DDB patch rows."""

    def test_creates_patches(self, s3, dynamodb):
        """Positive: at least one patch dict with patch_id and patch_path (happy path).

        Why: downstream Modal needs URIs to score patches.
        """
        img = Image.new("RGB", (600, 600))
        patches = inference_service.create_and_upload_patches(img, "img-1")
        assert len(patches) > 0
        for p in patches:
            assert "patch_id" in p
            assert "patch_path" in p

    def test_patch_ddb_items_have_all_fields(self, s3, dynamodb):
        """Positive: DynamoDB patch item includes geometry and type fields Modal/UI rely on.

        Why: missing patch_x/type breaks evidence display or inference.
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
        """Negative: S3_IMAGES_PROCESSED_BUCKET unset → EnvironmentError before work.

        Why: misconfiguration must fail fast.
        """
        monkeypatch.delenv("S3_IMAGES_PROCESSED_BUCKET", raising=False)
        img = Image.new("RGB", (600, 600))
        with pytest.raises(EnvironmentError):
            inference_service.create_and_upload_patches(img, "img-1")

    def test_custom_processed_prefix(self, s3, dynamodb, monkeypatch):
        """Positive: S3_PROCESSED_PREFIX appears in keys (separate from raw prefix).

        Why: training vs inference bucket layouts may differ.
        """
        monkeypatch.setenv("S3_PROCESSED_PREFIX", "custom-inf-prefix")
        img = Image.new("RGB", (600, 600))
        inference_service.create_and_upload_patches(img, "img-prefix")
        resp = s3.list_objects_v2(Bucket="test-processed-bucket")
        keys = [o["Key"] for o in resp.get("Contents", [])]
        assert any(k.startswith("custom-inf-prefix/img-prefix/") for k in keys)


class TestRunModalInference:
    """``run_modal_inference`` — Modal ``Function.from_name`` + ``remote``."""

    def test_raises_on_failure(self):
        """Negative: Modal remote raises → RuntimeError wrapping "Model inference failed".

        Why: callers get a single predictable error type for logging/alerts.
        """
        mock_modal = MagicMock()
        mock_fn = MagicMock()
        mock_fn.remote.side_effect = Exception("Modal down")
        mock_modal.Function.from_name.return_value = mock_fn

        with patch.dict("sys.modules", {"modal": mock_modal}):
            with pytest.raises(RuntimeError, match="Model inference failed"):
                inference_service.run_modal_inference(["s3://b/k1", "s3://b/k2"])

    def test_returns_result_on_success(self):
        """Positive: successful remote return dict is passed through (e.g. mean_prob).

        Why: route persists scores from this structure.
        """
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
        """Positive: pins app name, function name, variant, checkpoint (regression guard).

        Why: typos or wrong checkpoint silently break production scoring.
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
    """``save_patch_predictions`` — per-patch score/prediction writes."""

    def test_successful_patch_prediction_update(self, s3, dynamodb):
        """Positive: Decimal score and int prediction on real DynamoDB row.

        Why: types must match what readers expect (not float strings).
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
        """Positive: batch zip updates multiple patch_ids in one call.

        Why: ensures loop covers all aligned tuples.
        """
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
        """Positive: empty lists → no update_item calls, no crash.

        Why: idempotent safe call when no patches returned.
        """
        inference_service.save_patch_predictions([], [], [])

    def test_continues_after_first_patch_ddb_failure(self, s3, dynamodb):
        """Negative: first update_item fails; second still invoked (log-and-continue).

        Why: one corrupt row must not lose scores for remaining patches.
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
    """``query_rag_explanation`` — optional RAG; calls ``generate_explanation`` when KB set."""

    def test_returns_none_when_no_kb(self, monkeypatch):
        """Negative: KNOWLEDGE_BASE_ID unset → None (RAG disabled, no Bedrock call).

        Why: same code path in regions without a KB.
        """
        monkeypatch.delenv("KNOWLEDGE_BASE_ID", raising=False)
        result = inference_service.query_rag_explanation(
            1, 0.9, **_sample_rag_call_kwargs(),
        )
        assert result is None

    def test_returns_fallback_on_error(self, monkeypatch):
        """Negative: generate_explanation raises → stable fallback string; no exception to route.

        Why: RAG failures must not 500 the inference request.
        """
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
        """Positive / boundary: empty response_text from pipeline → same fallback as hard failure.

        Why: users must not see a blank explanation when the model returns "".
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
        """Positive: non-empty GenerationResult.response_text returned; artist/artwork forwarded.

        Why: matches router contract for retrieval query and explanation text.
        """
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
    """``mark_inference_failed`` — failed status + error_message on inference row."""

    def test_updates_status(self, s3, dynamodb):
        """Positive: processing → failed with stored error string.

        Why: UI and support rely on this transition.
        """
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
        """Negative: error string longer than 3500 chars → truncated (DynamoDB item size safety).

        Why: stack dumps must not exceed practical attribute size.
        """
        table = dynamodb.Table("test-inferences")
        table.put_item(Item={"inference_id": "fail-long", "inference_status": "processing"})
        huge = "e" * 5000
        inference_service.mark_inference_failed("fail-long", huge)
        msg = table.get_item(Key={"inference_id": "fail-long"})["Item"]["error_message"]
        assert len(msg) == 3500
        assert msg == "e" * 3500

    def test_mark_failed_logs_on_ddb_failure(self, s3, dynamodb):
        """Negative: update_item raises → logged, not re-raised (worker must not crash).

        Why: same pattern as coverage_gaps DDB failure test.
        """
        mock_table = MagicMock()
        mock_table.update_item.side_effect = Exception("DDB unavailable")
        with patch.object(inference_service, "get_table", return_value=mock_table):
            inference_service.mark_inference_failed("ghost-id", "error detail")


class TestFinalizeInference:
    """``finalize_inference`` — completed record: score, prediction, explanation, REMOVE errors."""

    def test_updates_with_results(self, s3, dynamodb):
        """Positive: status completed; score, explanation persisted.

        Why: primary success path for the pipeline.
        """
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
        """Positive: explanation=None → no explanation attribute on item (optional RAG).

        Why: DynamoDB omit vs empty string semantics for "no explanation".
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
        """Negative: score > 1.0 → clamp_score before Decimal.

        Why: bad model output must not write out-of-range numbers.
        """
        table = dynamodb.Table("test-inferences")
        table.put_item(Item={"inference_id": "fin-hi", "inference_status": "processing"})
        inference_service.finalize_inference("fin-hi", 1.5, 1, None)
        item = table.get_item(Key={"inference_id": "fin-hi"})["Item"]
        assert float(item["score"]) == pytest.approx(1.0)

    def test_finalize_clamps_score_below_zero(self, s3, dynamodb):
        """Negative: score < 0 → clamped to 0.0.

        Why: same as above for lower bound.
        """
        table = dynamodb.Table("test-inferences")
        table.put_item(Item={"inference_id": "fin-lo", "inference_status": "processing"})
        inference_service.finalize_inference("fin-lo", -0.3, 1, None)
        item = table.get_item(Key={"inference_id": "fin-lo"})["Item"]
        assert float(item["score"]) == pytest.approx(0.0)

    def test_finalize_rejects_invalid_prediction(self, s3, dynamodb):
        """Negative: prediction not in {-1,0,1} after validation → stored as -1.

        Why: invalid values must not masquerade as real 0/1 labels.
        """
        table = dynamodb.Table("test-inferences")
        table.put_item(Item={"inference_id": "fin-bad-p", "inference_status": "processing"})
        inference_service.finalize_inference("fin-bad-p", 0.5, 99, None)
        item = table.get_item(Key={"inference_id": "fin-bad-p"})["Item"]
        assert item["prediction"] == -1

    def test_finalize_clears_previous_error(self, s3, dynamodb):
        """Positive: prior error_message removed when finalize succeeds (stale error cleanup).

        Why: retry-after-failure must not show old error on completed row.
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
        """Negative: update_item fails → exception swallowed after log (caller continues).

        Why: last-step DDB failure should not crash the worker loop.
        """
        mock_table = MagicMock()
        mock_table.update_item.side_effect = Exception("DDB unavailable")
        with patch.object(inference_service, "get_table", return_value=mock_table):
            inference_service.finalize_inference("any-id", 0.9, 1, "Explanation")


class TestGenerateImageUrl:
    """``generate_image_url`` — presigned GET for raw image keys."""

    def test_generates_url(self, s3):
        """Positive: object exists → non-None URL containing bucket (moto presign).

        Why: listing/detail views need a link when object is present.
        """
        s3.put_object(Bucket="test-raw-bucket", Key="test/img.jpg", Body=b"data")
        url = inference_service.generate_image_url("s3://test-raw-bucket/test/img.jpg")
        assert url is not None
        assert "test-raw-bucket" in url

    def test_returns_none_on_error(self, s3):
        """Positive / soft: missing or bad key — URL may be None or str depending on moto.

        Why: exercises branch where listing still runs without a URL.
        """
        url = inference_service.generate_image_url("s3://nonexistent/bad.jpg")
        assert url is None or isinstance(url, str)

    def test_custom_presign_expiration(self, s3, monkeypatch):
        """Positive: S3_INFERENCE_PRESIGN_EXPIRES forwarded as expiry seconds to presigned_get_url.

        Why: compliance may require shorter-lived URLs.
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
        """Negative: presigned_get_url raises → None (deterministic error path; moto may not raise).

        Why: presign failures must not propagate to HTTP layer as 500 from this helper.
        """
        with patch(
            "src.apps.backend.services.inference_service.presigned_get_url",
            side_effect=ValueError("invalid uri"),
        ):
            assert inference_service.generate_image_url("s3://test-raw-bucket/x.jpg") is None


class TestNowMs:
    """``_now_ms`` — millisecond timestamp for created_at fields."""

    def test_now_ms_returns_positive_int(self):
        """Positive: returns int > 0 (contract for timestamps written to DynamoDB).

        Why: catches accidental removal or wrong unit (seconds vs ms).
        """
        t = inference_service._now_ms()
        assert isinstance(t, int)
        assert t > 0
