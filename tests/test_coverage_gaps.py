"""Tests targeting specific uncovered lines to maximize code coverage.

Each test class targets a specific file's uncovered lines identified
by the coverage report.
"""

import time
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# logging_config.py — lines 45, 55 (context var getters)
# ---------------------------------------------------------------------------

class TestLoggingContextVars:
    """Cover get_request_id and get_context_user_id."""

    def test_get_request_id_default(self):
        from src.apps.backend.logging_config import get_request_id, set_request_id
        set_request_id("")
        assert get_request_id() == ""

    def test_get_request_id_set(self):
        from src.apps.backend.logging_config import get_request_id, set_request_id
        set_request_id("abc-123")
        assert get_request_id() == "abc-123"
        set_request_id("")

    def test_get_context_user_id_default(self):
        from src.apps.backend.logging_config import get_context_user_id, set_context_user_id
        set_context_user_id("")
        assert get_context_user_id() == ""

    def test_get_context_user_id_set(self):
        from src.apps.backend.logging_config import get_context_user_id, set_context_user_id
        set_context_user_id("user-42")
        assert get_context_user_id() == "user-42"
        set_context_user_id("")


# ---------------------------------------------------------------------------
# auth_router.py — lines 151 (me: user not found), 171 (profile: email taken
# by another user), 193 (change-password: user not found)
# ---------------------------------------------------------------------------

class TestAuthRouterEdgeCases:
    """Cover error branches in auth routes that require deleted/missing users."""

    @pytest.mark.asyncio
    async def test_me_user_deleted_after_token_issued(self, client, dynamodb):
        """GET /auth/me returns 404 if the user was deleted after token was created."""
        from src.apps.backend.security.jwt_tokens import create_access_token
        token = create_access_token("deleted-user-id")
        headers = {"Authorization": f"Bearer {token}"}
        # User doesn't exist in DynamoDB — should get 404
        resp = await client.get("/auth/me", headers=headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_profile_email_taken_by_other(self, client, create_test_user, dynamodb):
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


# ---------------------------------------------------------------------------
# inferences_router.py — lines 83-85 (_float_score edge cases),
# 156-159 (presign failure), 166-167 (bad prediction), 200-201 (missing table)
# ---------------------------------------------------------------------------

class TestInferencesRouterEdgeCases:
    """Cover edge cases in inferences_router helper functions and error branches."""

    def test_float_score_none(self):
        from src.apps.backend.routes.inferences_router import _float_score
        assert _float_score(None) == 0.0

    def test_float_score_plain_float(self):
        from src.apps.backend.routes.inferences_router import _float_score
        assert _float_score(0.75) == 0.75

    def test_float_score_string_number(self):
        from src.apps.backend.routes.inferences_router import _float_score
        assert _float_score("0.5") == 0.5

    @pytest.mark.asyncio
    async def test_inference_with_bad_prediction_value(self, client, auth_headers, dynamodb):
        """GET /inferences should handle non-numeric prediction gracefully."""
        table = dynamodb.Table("test-inferences")
        table.put_item(Item={
            "inference_id": "bad-pred",
            "user_id": "test-user-1",
            "created_at": int(time.time() * 1000),
            "score": Decimal("0.5"),
            "prediction": "not-a-number",  # Bad data
            "artist_name": "Test",
            "artwork_name": "Test",
            "image_name": "test.jpg",
            "file_size": 100,
            "image_path": "",
        })
        resp = await client.get("/inferences", headers=auth_headers)
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["prediction"] is None  # Gracefully set to None

    @pytest.mark.asyncio
    async def test_inference_with_presign_failure(self, client, auth_headers, dynamodb):
        """GET /inferences handles presign failures gracefully (empty url)."""
        table = dynamodb.Table("test-inferences")
        table.put_item(Item={
            "inference_id": "presign-fail",
            "user_id": "test-user-1",
            "created_at": int(time.time() * 1000),
            "score": Decimal("0.8"),
            "prediction": 1,
            "artist_name": "Test",
            "artwork_name": "Test",
            "image_name": "test.jpg",
            "file_size": 100,
            "image_path": "s3://nonexistent-bucket-xyz/bad/path.jpg",
        })
        resp = await client.get("/inferences", headers=auth_headers)
        assert resp.status_code == 200
        # Should not crash, image_url will be empty or have the presigned url

    @pytest.mark.asyncio
    async def test_inferences_missing_table_config(self, client, auth_headers, monkeypatch, mock_aws_services):
        """GET /inferences/stats returns 500 if DDB_INFERENCES_TABLE is not set."""
        monkeypatch.delenv("DDB_INFERENCES_TABLE", raising=False)
        resp = await client.get("/inferences/stats", headers=auth_headers)
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# inference_service.py — lines 294-295 (patch save failure), 383-384
# (finalize failure), 406-407 (mark_failed failure), 426-428 (presign failure)
# ---------------------------------------------------------------------------

class TestInferenceServiceErrorBranches:
    """Cover error-handling branches in inference_service."""

    def test_save_patch_predictions_handles_ddb_error(self, s3, dynamodb):
        """save_patch_predictions should log and continue on DynamoDB failure."""
        from src.apps.backend.services import inference_service

        patches = [{"patch_id": "p1"}, {"patch_id": "p2"}]
        # Monkeypatch the table to raise on update_item
        with patch.object(inference_service, "get_table") as mock_get_table:
            mock_table = MagicMock()
            mock_table.update_item.side_effect = Exception("DDB write failed")
            mock_get_table.return_value = mock_table

            # Should NOT raise — logs warning and continues
            inference_service.save_patch_predictions(patches, [0.9, 0.8], [1, 1])

    def test_finalize_inference_handles_ddb_error(self, s3, dynamodb):
        """finalize_inference should log error on DynamoDB failure."""
        from src.apps.backend.services import inference_service

        with patch.object(inference_service, "get_table") as mock_get_table:
            mock_table = MagicMock()
            mock_table.update_item.side_effect = Exception("DDB down")
            mock_get_table.return_value = mock_table

            # Should NOT raise
            inference_service.finalize_inference("inf-1", 0.9, 1, "Explanation")

    def test_mark_inference_failed_handles_ddb_error(self, s3, dynamodb):
        """mark_inference_failed should log error on DynamoDB failure."""
        from src.apps.backend.services import inference_service

        with patch.object(inference_service, "get_table") as mock_get_table:
            mock_get_table.side_effect = Exception("Table not found")

            # Should NOT raise
            inference_service.mark_inference_failed("inf-1", "some error")

    def test_generate_image_url_handles_presign_error(self, s3):
        """generate_image_url returns None on presign failure."""
        from src.apps.backend.services import inference_service

        with patch("src.apps.backend.services.inference_service.presigned_get_url") as mock_presign:
            mock_presign.side_effect = Exception("Presign failed")
            result = inference_service.generate_image_url("s3://bucket/key.jpg")
            assert result is None

    def test_query_rag_explanation_success_path(self, monkeypatch):
        """Cover the successful RAG query path with metrics emission."""
        from src.apps.backend.services import inference_service

        monkeypatch.setenv("KNOWLEDGE_BASE_ID", "kb-test")

        mock_bedrock = MagicMock()
        mock_bedrock.retrieve_and_generate.return_value = {
            "output": {"text": "This artwork appears authentic based on..."}
        }

        with patch("src.apps.backend.services.inference_service.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_bedrock
            with patch("src.apps.backend.services.inference_service.emit_metric"):
                result = inference_service.query_rag_explanation(1, 0.92)
                assert "authentic" in result.lower()


# ---------------------------------------------------------------------------
# users_service.py — lines 100 (unexpected ClientError re-raise),
# 127-129 (update_profile ClientError), 133 (user not found after update),
# 153-155 (update_password ClientError)
# ---------------------------------------------------------------------------

class TestUsersServiceErrorBranches:
    """Cover error branches in users_service."""

    def test_create_user_unexpected_ddb_error(self, dynamodb):
        """create_user re-raises unexpected ClientErrors (not ConditionalCheck)."""
        from src.apps.backend.services import users_service
        from botocore.exceptions import ClientError

        with patch.object(users_service, "_table") as mock_table_fn:
            mock_table = MagicMock()
            mock_table.put_item.side_effect = ClientError(
                {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "Throttled"}},
                "PutItem",
            )
            mock_table_fn.return_value = mock_table

            with pytest.raises(ClientError):
                users_service.create_user("u1", "e@e.com", "name", "hash")

    def test_update_profile_ddb_error(self, dynamodb, create_test_user):
        """update_user_profile re-raises ClientError from DynamoDB."""
        from src.apps.backend.services import users_service
        from botocore.exceptions import ClientError

        create_test_user(user_id="err-user", email="err@e.com")

        with patch.object(users_service, "_table") as mock_table_fn:
            mock_table = MagicMock()
            mock_table.update_item.side_effect = ClientError(
                {"Error": {"Code": "InternalServerError", "Message": "DDB down"}},
                "UpdateItem",
            )
            mock_table_fn.return_value = mock_table

            with pytest.raises(ClientError):
                users_service.update_user_profile("err-user", "new", "err@e.com")

    def test_update_password_ddb_error(self, dynamodb, create_test_user):
        """update_password_hash re-raises ClientError from DynamoDB."""
        from src.apps.backend.services import users_service
        from botocore.exceptions import ClientError

        create_test_user(user_id="pw-err", email="pw@e.com")

        with patch.object(users_service, "_table") as mock_table_fn:
            mock_table = MagicMock()
            mock_table.update_item.side_effect = ClientError(
                {"Error": {"Code": "InternalServerError", "Message": "DDB down"}},
                "UpdateItem",
            )
            mock_table_fn.return_value = mock_table

            with pytest.raises(ClientError):
                users_service.update_password_hash("pw-err", "newhash")

    def test_update_profile_user_gone_after_update(self, dynamodb):
        """update_user_profile raises ValueError if user vanishes between update and re-fetch.

        This covers line 133 — a defensive check for the (rare) case where
        DynamoDB's update_item succeeds but the subsequent get_item returns None
        (e.g., concurrent delete or eventual consistency).
        """
        from src.apps.backend.services import users_service

        # Mock _table so update_item succeeds, but get_user_by_id returns None
        with patch.object(users_service, "_table") as mock_table_fn:
            mock_table = MagicMock()
            mock_table.update_item.return_value = {}  # success
            mock_table_fn.return_value = mock_table

            with patch.object(users_service, "get_user_by_id", return_value=None):
                with pytest.raises(ValueError, match="not found after update"):
                    users_service.update_user_profile("vanished-user", "name", "e@e.com")


# ---------------------------------------------------------------------------
# driver.py — line 247 (update existing image record), 355-357 (process error)
# ---------------------------------------------------------------------------

class TestDriverEdgeCases:
    """Cover edge cases in the data pipeline driver."""

    def test_process_single_image_existing_record(self, s3, dynamodb):
        """When an ImageRecord already exists, driver should update run_id."""
        from io import BytesIO
        from PIL import Image
        from src.apps.data_pipeline.driver import process_single_image

        # Pre-create the image record
        img_table = dynamodb.Table("test-images")
        img_table.put_item(Item={
            "image_id": "existing-id",
            "image_name": "old.jpg",
            "label": "authentic",
        })

        # Upload image to S3 with the known image_id in path
        img = Image.new("RGB", (600, 600), color="green")
        buf = BytesIO()
        img.save(buf, format="JPEG")
        s3.put_object(
            Bucket="test-raw-bucket",
            Key="training/unprocessed/existing-id/photo.jpg",
            Body=buf.getvalue(),
        )

        patch_table = dynamodb.Table("test-patches")
        n = process_single_image(
            s3_client=s3,
            img_table=img_table,
            patch_table=patch_table,
            raw_bucket="test-raw-bucket",
            processed_bucket="test-processed-bucket",
            key="training/unprocessed/existing-id/photo.jpg",
            run_id="run-xyz",
        )
        assert n > 0

        # Verify run_id was updated on existing record
        resp = img_table.get_item(Key={"image_id": "existing-id"})
        assert resp["Item"]["run_id"] == "run-xyz"
        # Original label should still be there
        assert resp["Item"]["label"] == "authentic"


# ---------------------------------------------------------------------------
# wikidata_pipeline.py — lines 171,173,175,177 (multi-value field collection)
# ---------------------------------------------------------------------------

class TestWikidataMultiValueFields:
    """Cover all multi-value field collection branches in build_rag_document."""

    def test_all_multi_value_fields(self):
        from src.apps.data_pipeline.wikidata_pipeline import build_rag_document

        result = {
            "results": {
                "bindings": [
                    {
                        "artistLabel": {"value": "Test Artist"},
                        "movementLabel": {"value": "Cubism"},
                        "genreLabel": {"value": "Portrait"},
                        "occupationLabel": {"value": "Painter"},
                        "fieldLabel": {"value": "Visual arts"},
                        "influencedByLabel": {"value": "Picasso"},
                        "notableWorkLabel": {"value": "Guernica"},
                    },
                    {
                        "artistLabel": {"value": "Test Artist"},
                        "movementLabel": {"value": "Surrealism"},
                        "genreLabel": {"value": "Landscape"},
                        "occupationLabel": {"value": "Sculptor"},
                        "fieldLabel": {"value": "Fine arts"},
                        "influencedByLabel": {"value": "Dalí"},
                        "notableWorkLabel": {"value": "The Persistence of Memory"},
                    },
                ]
            }
        }
        doc = build_rag_document(result)
        assert "Cubism" in doc
        assert "Surrealism" in doc
        assert "Painter" in doc
        assert "Sculptor" in doc
        assert "Visual arts" in doc
        assert "Fine arts" in doc
        assert "Picasso" in doc
        assert "Dalí" in doc  # note: accented character
        assert "Guernica" in doc
        assert "The Persistence of Memory" in doc


# ---------------------------------------------------------------------------
# met_pipeline.py — lines 123, 125-126 (progress log and max record limit)
# ---------------------------------------------------------------------------

class TestMetPipelineEdgeCases:
    """Cover progress logging and MAX_RECORDS limit in met_pipeline."""

    def test_max_records_limit(self, tmp_path, monkeypatch):
        """Pipeline should stop after MAX_RECORDS."""
        import csv
        from contextlib import contextmanager

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()

        csv_path = str(src_dir / "MetObjects.csv")
        fieldnames = ["Artist Display Name", "Title"]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for i in range(10):
                writer.writerow({
                    "Artist Display Name": f"Artist {i}",
                    "Title": f"Work {i}",
                })

        output_file = str(tmp_path / "output.jsonl")
        monkeypatch.setattr("src.apps.data_pipeline.met_pipeline.OUTPUT_FILE", output_file)
        monkeypatch.setattr("src.apps.data_pipeline.met_pipeline.MAX_RECORDS", 3)

        @contextmanager
        def mock_urlopen(url):
            yield open(csv_path, "rb")

        monkeypatch.setattr(
            "src.apps.data_pipeline.met_pipeline.urllib.request.urlopen",
            mock_urlopen,
        )
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(temp_dir))

        from src.apps.data_pipeline.met_pipeline import main
        main()

        import json
        with open(output_file) as f:
            lines = f.readlines()
        assert len(lines) == 3  # Stopped at MAX_RECORDS

    def test_progress_log_at_10000(self, tmp_path, monkeypatch, capsys):
        """Covers line 123: progress print when count hits a multiple of 10000.

        Generates 10001 CSV rows so the pipeline emits the '10000 records'
        progress message. Uses MAX_RECORDS=10001 to let it run that far.
        """
        import csv
        from contextlib import contextmanager

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()

        csv_path = str(src_dir / "MetObjects.csv")
        fieldnames = ["Artist Display Name", "Title"]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for i in range(10001):
                writer.writerow({
                    "Artist Display Name": f"Artist {i}",
                    "Title": f"Work {i}",
                })

        output_file = str(tmp_path / "output.jsonl")
        monkeypatch.setattr("src.apps.data_pipeline.met_pipeline.OUTPUT_FILE", output_file)
        monkeypatch.setattr("src.apps.data_pipeline.met_pipeline.MAX_RECORDS", 10001)

        @contextmanager
        def mock_urlopen(url):
            yield open(csv_path, "rb")

        monkeypatch.setattr(
            "src.apps.data_pipeline.met_pipeline.urllib.request.urlopen",
            mock_urlopen,
        )
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(temp_dir))

        from src.apps.data_pipeline.met_pipeline import main
        main()

        captured = capsys.readouterr()
        assert "10000 records" in captured.out


# ---------------------------------------------------------------------------
# inference_router.py — lines 138-140 (generic Exception during pipeline prep)
# ---------------------------------------------------------------------------

class TestInferenceRouterGenericError:
    """Cover the generic Exception handler in the inference pipeline prep phase.

    Line 138-140: when an unexpected error (not EnvironmentError) occurs during
    S3 upload, DynamoDB writes, or patch creation, the route returns 500 with
    'Failed to process the uploaded image'.
    """

    @pytest.mark.asyncio
    async def test_generic_pipeline_error_500(self, client, auth_headers, sample_image_bytes, s3, dynamodb):
        """A non-EnvironmentError exception during patch creation returns 500."""
        # upload_raw_image and save_image_metadata succeed, but create_and_upload_patches crashes
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


# ---------------------------------------------------------------------------
# inferences_router.py — lines 158-159 (presign failure in _item_to_list_item)
# ---------------------------------------------------------------------------

class TestInferencesPresignFailure:
    """Cover the presigned URL failure branch inside _item_to_list_item.

    Lines 158-159: when presigned_get_url raises for a specific inference's
    image_path, the item should still be returned with an empty image_url
    instead of crashing the entire list response.
    """

    @pytest.mark.asyncio
    async def test_presign_failure_returns_empty_url(self, client, auth_headers, dynamodb):
        """List inferences succeeds even when presigning one image fails."""
        table = dynamodb.Table("test-inferences")
        table.put_item(Item={
            "inference_id": "presign-err-1",
            "user_id": "test-user-1",
            "created_at": int(time.time() * 1000),
            "score": Decimal("0.9"),
            "prediction": 1,
            "inference_status": "completed",
            "artist_name": "Test",
            "artwork_name": "Test",
            "image_name": "test.jpg",
            "file_size": 100,
            "image_path": "s3://bucket/key.jpg",
        })

        # Force presigned_get_url to raise
        with patch(
            "src.apps.backend.routes.inferences_router.presigned_get_url",
            side_effect=Exception("Presign failed"),
        ):
            resp = await client.get("/inferences", headers=auth_headers)
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert len(items) == 1
            # image_url should be empty string (not crash)
            assert items[0]["image_url"] == ""


# ---------------------------------------------------------------------------
# driver.py — lines 355-357 (process_single_image error during batch run)
# ---------------------------------------------------------------------------

class TestDriverProcessingError:
    """Cover the error branch in the driver's main processing loop.

    Lines 355-357: when process_single_image raises for one image, the driver
    logs the error and continues to the next image instead of crashing.
    """

    def test_processing_error_continues_to_next_image(self, s3, dynamodb, monkeypatch):
        """Driver should mark run as 'completed_with_errors' when process_single_image raises.

        Covers lines 355-357: the except branch that increments the error counter
        and logs the failure, allowing the loop to continue to the next image.
        We mock process_single_image to raise on the first call and succeed on
        the second, then verify the run status reflects the partial failure.
        """
        from io import BytesIO
        from PIL import Image
        from src.apps.data_pipeline import driver

        monkeypatch.setenv("S3_IMAGES_RAW_BUCKET", "test-raw-bucket")
        monkeypatch.setenv("S3_IMAGES_PROCESSED_BUCKET", "test-processed-bucket")
        monkeypatch.setenv("DDB_IMAGES_TABLE", "test-images")
        monkeypatch.setenv("DDB_PATCHES_TABLE", "test-patches")
        monkeypatch.setenv("DDB_RUNS_TABLE", "test-runs")

        # Upload two images so the loop runs twice
        for name in ("img-a", "img-b"):
            img = Image.new("RGB", (600, 600), color="blue")
            buf = BytesIO()
            img.save(buf, format="JPEG")
            s3.put_object(
                Bucket="test-raw-bucket",
                Key=f"training/unprocessed/{name}/photo.jpg",
                Body=buf.getvalue(),
            )

        # First call raises (triggers the except branch), second succeeds
        original = driver.process_single_image
        call_count = {"n": 0}

        def mock_process(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("Simulated processing failure")
            return original(*args, **kwargs)

        with patch("sys.argv", ["driver", "--run_id", "err-run"]):
            with patch.object(driver, "process_single_image", side_effect=mock_process):
                driver.main()

        runs_table = dynamodb.Table("test-runs")
        resp = runs_table.get_item(Key={"run_id": "err-run"})
        assert resp["Item"]["status"] == "completed_with_errors"


# ---------------------------------------------------------------------------
# wikidata_pipeline.py — lines 213-226 (main function)
# ---------------------------------------------------------------------------

class TestWikidataPipelineMain:
    """Cover the wikidata_pipeline main() orchestrator.

    Lines 213-226: iterates over ARTISTS dict, queries Wikidata for each,
    builds RAG documents, and exports to JSONL.
    """

    def test_main_queries_and_exports(self, tmp_path, monkeypatch):
        """main() should query each artist and write output JSONL."""
        from src.apps.data_pipeline import wikidata_pipeline

        output_file = str(tmp_path / "wiki_output.jsonl")
        monkeypatch.setattr(wikidata_pipeline, "OUTPUT_FILE", output_file)
        # Use a small artist set for speed
        monkeypatch.setattr(wikidata_pipeline, "ARTISTS", {"TestArtist": "Q12345"})

        fake_result = {
            "results": {
                "bindings": [{
                    "artistLabel": {"value": "TestArtist"},
                    "description": {"value": "A test artist"},
                    "birth": {"value": "1900"},
                    "death": {"value": "2000"},
                    "citizenshipLabel": {"value": "Testland"},
                }]
            }
        }
        monkeypatch.setattr(wikidata_pipeline, "query_wikidata", lambda q: fake_result)

        wikidata_pipeline.main()

        import json
        with open(output_file) as f:
            lines = f.readlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["id"] == "Q12345"
        assert "TestArtist" in record["text"]

    def test_main_skips_empty_rag_text(self, tmp_path, monkeypatch):
        """Artists with no Wikidata bindings produce no output records."""
        from src.apps.data_pipeline import wikidata_pipeline

        output_file = str(tmp_path / "wiki_empty.jsonl")
        monkeypatch.setattr(wikidata_pipeline, "OUTPUT_FILE", output_file)
        monkeypatch.setattr(wikidata_pipeline, "ARTISTS", {"NoData": "Q00000"})

        # Empty bindings → build_rag_document returns None
        empty_result = {"results": {"bindings": []}}
        monkeypatch.setattr(wikidata_pipeline, "query_wikidata", lambda q: empty_result)

        wikidata_pipeline.main()

        with open(output_file) as f:
            lines = f.readlines()
        assert len(lines) == 0  # No records written
