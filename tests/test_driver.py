"""Tests for src.apps.data_pipeline.driver — ECS Fargate processing task."""

import os
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from src.apps.data_pipeline.driver import (
    download,
    extract_image_id,
    image_record_exists,
    list_unprocessed_keys,
    move_to_processed,
    now_ms,
    process_single_image,
    write_patch_records,
    _require_env,
)


class TestNowMs:
    """Tests for now_ms."""

    def test_returns_positive_int(self):
        result = now_ms()
        assert isinstance(result, int)
        assert result > 0

    def test_millisecond_precision(self):
        result = now_ms()
        assert result > 1_000_000_000_000  # After 2001 in ms


class TestRequireEnv:
    """Tests for _require_env."""

    def test_returns_value(self, monkeypatch):
        monkeypatch.setenv("TEST_X", "hello")
        assert _require_env("TEST_X") == "hello"

    def test_raises_when_missing(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        with pytest.raises(EnvironmentError, match="MISSING_VAR"):
            _require_env("MISSING_VAR")


class TestExtractImageId:
    """Tests for extract_image_id."""

    def test_standard_path(self):
        result = extract_image_id("training/unprocessed/abc-123/photo.jpg")
        assert result == "abc-123"

    def test_flat_path_returns_none(self):
        result = extract_image_id("training/unprocessed/photo.jpg")
        assert result is None

    def test_deep_path(self):
        result = extract_image_id("training/unprocessed/id-1/subdir/file.jpg")
        assert result == "id-1"

    def test_empty_string(self):
        result = extract_image_id("")
        assert result is None


class TestImageRecordExists:
    """Tests for image_record_exists."""

    def test_exists(self, dynamodb):
        table = dynamodb.Table("test-images")
        table.put_item(Item={"image_id": "exists-1", "image_name": "test.jpg"})
        assert image_record_exists(table, "exists-1") is True

    def test_not_exists(self, dynamodb):
        table = dynamodb.Table("test-images")
        assert image_record_exists(table, "missing") is False


class TestDownload:
    """Tests for download."""

    def test_downloads_object(self, s3):
        s3.put_object(Bucket="test-raw-bucket", Key="test/file.jpg", Body=b"image-data")
        result = download(s3, "test-raw-bucket", "test/file.jpg")
        assert result == b"image-data"

    def test_raises_ioerror_on_failure(self):
        mock_s3 = MagicMock()
        mock_s3.get_object.side_effect = Exception("AccessDenied")
        with pytest.raises(IOError, match="Failed to download"):
            download(mock_s3, "bad-bucket", "bad-key")


class TestListUnprocessedKeys:
    """Tests for list_unprocessed_keys."""

    def test_lists_image_files(self, s3):
        s3.put_object(Bucket="test-raw-bucket", Key="training/unprocessed/a.jpg", Body=b"x")
        s3.put_object(Bucket="test-raw-bucket", Key="training/unprocessed/b.png", Body=b"x")
        s3.put_object(Bucket="test-raw-bucket", Key="training/unprocessed/c.txt", Body=b"x")  # Not an image
        keys = list_unprocessed_keys(s3, "test-raw-bucket", "training/unprocessed/")
        assert len(keys) == 2
        assert any("a.jpg" in k for k in keys)
        assert any("b.png" in k for k in keys)

    def test_empty_prefix(self, s3):
        keys = list_unprocessed_keys(s3, "test-raw-bucket", "nonexistent/")
        assert keys == []


class TestWritePatchRecords:
    """Tests for write_patch_records."""

    def test_writes_all_patches(self, dynamodb):
        table = dynamodb.Table("test-patches")
        patches = [
            {"patch_id": "p1", "patch_type": "grid", "patch_path": "s3://b/k1",
             "patch_x": 0, "patch_y": 0, "patch_width": 224, "patch_height": 224},
            {"patch_id": "p2", "patch_type": "center", "patch_path": "s3://b/k2",
             "patch_x": 100, "patch_y": 100, "patch_width": 224, "patch_height": 224},
        ]
        write_patch_records(table, "img-1", patches, 1700000000000)

        resp = table.get_item(Key={"patch_id": "p1"})
        assert resp["Item"]["image_id"] == "img-1"


class TestMoveToProcessed:
    """Tests for move_to_processed."""

    def test_raises_ioerror_on_failure(self):
        mock_s3 = MagicMock()
        mock_s3.copy_object.side_effect = Exception("AccessDenied")
        with pytest.raises(IOError, match="Failed to move"):
            move_to_processed(mock_s3, "bucket", "training/unprocessed/img/f.jpg")

    def test_moves_object(self, s3):
        s3.put_object(
            Bucket="test-raw-bucket",
            Key="training/unprocessed/img-1/photo.jpg",
            Body=b"data",
        )
        move_to_processed(s3, "test-raw-bucket", "training/unprocessed/img-1/photo.jpg")

        # Original should be gone
        with pytest.raises(Exception):
            s3.get_object(Bucket="test-raw-bucket", Key="training/unprocessed/img-1/photo.jpg")

        # New location should exist
        resp = s3.get_object(
            Bucket="test-raw-bucket",
            Key="training/processed/img-1/photo.jpg",
        )
        assert resp["Body"].read() == b"data"


class TestProcessSingleImage:
    """Tests for process_single_image."""

    def test_processes_valid_image(self, s3, dynamodb):
        # Upload a valid JPEG to S3
        img = Image.new("RGB", (600, 600), color="blue")
        buf = BytesIO()
        img.save(buf, format="JPEG")

        s3.put_object(
            Bucket="test-raw-bucket",
            Key="training/unprocessed/test-id/photo.jpg",
            Body=buf.getvalue(),
        )

        img_table = dynamodb.Table("test-images")
        patch_table = dynamodb.Table("test-patches")

        n_patches = process_single_image(
            s3_client=s3,
            img_table=img_table,
            patch_table=patch_table,
            raw_bucket="test-raw-bucket",
            processed_bucket="test-processed-bucket",
            key="training/unprocessed/test-id/photo.jpg",
            run_id="run-1",
        )
        assert n_patches > 0

    def test_skips_invalid_image(self, s3, dynamodb):
        s3.put_object(
            Bucket="test-raw-bucket",
            Key="training/unprocessed/bad/notimage.jpg",
            Body=b"not an image",
        )
        img_table = dynamodb.Table("test-images")
        patch_table = dynamodb.Table("test-patches")

        n = process_single_image(
            s3_client=s3,
            img_table=img_table,
            patch_table=patch_table,
            raw_bucket="test-raw-bucket",
            processed_bucket="test-processed-bucket",
            key="training/unprocessed/bad/notimage.jpg",
            run_id="run-2",
        )
        assert n == 0
