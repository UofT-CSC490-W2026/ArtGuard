"""Tests for src.apps.train.dataset — S3/DynamoDB patch streaming dataset.

All AWS calls are mocked — no real S3 or DynamoDB connections needed.
Requires torch — skipped entirely if torch is not installed (e.g. GitHub Actions CI).
"""
import io

import pytest

pytest.importorskip("torch")
from PIL import Image
from unittest.mock import MagicMock, patch, PropertyMock
from torchvision import transforms

from src.apps.train.dataset import (
    IMAGENET_MEAN,
    IMAGENET_STD,
    _query_patches_for_image,
    _s3_path_to_bucket_key,
    _scan_all,
    _stream_patch_from_s3,
    default_train_transforms,
    default_val_transforms,
)


# ---------------------------------------------------------------------------
# Transform helpers
# ---------------------------------------------------------------------------

class TestTransforms:
    def test_train_transforms_type(self):
        t = default_train_transforms()
        assert isinstance(t, transforms.Compose)

    def test_val_transforms_type(self):
        t = default_val_transforms()
        assert isinstance(t, transforms.Compose)

    def test_train_transforms_include_flip(self):
        t = default_train_transforms()
        types = [type(x) for x in t.transforms]
        assert transforms.RandomHorizontalFlip in types

    def test_val_transforms_no_flip(self):
        t = default_val_transforms()
        types = [type(x) for x in t.transforms]
        assert transforms.RandomHorizontalFlip not in types

    def test_both_include_normalize(self):
        for fn in (default_train_transforms, default_val_transforms):
            t = fn()
            types = [type(x) for x in t.transforms]
            assert transforms.Normalize in types

    def test_imagenet_constants(self):
        assert len(IMAGENET_MEAN) == 3
        assert len(IMAGENET_STD) == 3
        assert all(0 < m < 1 for m in IMAGENET_MEAN)
        assert all(0 < s < 1 for s in IMAGENET_STD)


# ---------------------------------------------------------------------------
# _s3_path_to_bucket_key
# ---------------------------------------------------------------------------

class TestS3PathParse:
    def test_valid_uri(self):
        bucket, key = _s3_path_to_bucket_key("s3://my-bucket/path/to/file.png")
        assert bucket == "my-bucket"
        assert key == "path/to/file.png"

    def test_bucket_only(self):
        bucket, key = _s3_path_to_bucket_key("s3://my-bucket/")
        assert bucket == "my-bucket"
        assert key == ""

    def test_invalid_prefix(self):
        with pytest.raises(ValueError, match="Expected s3://"):
            _s3_path_to_bucket_key("https://example.com/file.png")

    def test_nested_path(self):
        bucket, key = _s3_path_to_bucket_key("s3://b/a/b/c/d.jpg")
        assert bucket == "b"
        assert key == "a/b/c/d.jpg"


# ---------------------------------------------------------------------------
# _stream_patch_from_s3
# ---------------------------------------------------------------------------

def _make_test_image_bytes():
    """Create a minimal JPEG image in memory."""
    img = Image.new("RGB", (10, 10), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf.read()


class TestStreamPatch:
    def test_s3_uri_path(self):
        mock_s3 = MagicMock()
        body = MagicMock()
        body.read.return_value = _make_test_image_bytes()
        mock_s3.get_object.return_value = {"Body": body}

        result = _stream_patch_from_s3(mock_s3, "s3://bucket/key.jpg")
        assert result.mode == "RGB"
        mock_s3.get_object.assert_called_once_with(Bucket="bucket", Key="key.jpg")

    def test_bare_key_path(self):
        mock_s3 = MagicMock()
        body = MagicMock()
        body.read.return_value = _make_test_image_bytes()
        mock_s3.get_object.return_value = {"Body": body}

        result = _stream_patch_from_s3(mock_s3, "training/img/patch.jpg", fallback_bucket="my-bucket")
        mock_s3.get_object.assert_called_once_with(Bucket="my-bucket", Key="training/img/patch.jpg")

    def test_bare_key_no_fallback_raises(self):
        mock_s3 = MagicMock()
        with pytest.raises(ValueError, match="fallback_bucket required"):
            _stream_patch_from_s3(mock_s3, "training/img/patch.jpg", fallback_bucket="")

    def test_no_such_key_propagates(self):
        from botocore.exceptions import ClientError

        mock_s3 = MagicMock()
        mock_s3.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "not found"}},
            "GetObject",
        )

        with pytest.raises(ClientError):
            _stream_patch_from_s3(mock_s3, "s3://bucket/missing.jpg")

    def test_generic_error_propagates(self):
        mock_s3 = MagicMock()
        mock_s3.get_object.side_effect = RuntimeError("connection timeout")

        with pytest.raises(RuntimeError, match="connection timeout"):
            _stream_patch_from_s3(mock_s3, "s3://bucket/bad.jpg")


# ---------------------------------------------------------------------------
# _scan_all
# ---------------------------------------------------------------------------

class TestScanAll:
    def test_single_page(self):
        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": [{"id": "1"}, {"id": "2"}]}
        result = _scan_all(mock_table)
        assert len(result) == 2

    def test_multiple_pages(self):
        mock_table = MagicMock()
        mock_table.scan.side_effect = [
            {"Items": [{"id": "1"}], "LastEvaluatedKey": {"id": "1"}},
            {"Items": [{"id": "2"}]},
        ]
        result = _scan_all(mock_table)
        assert len(result) == 2

    def test_empty_table(self):
        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": []}
        result = _scan_all(mock_table)
        assert result == []

    def test_passes_kwargs(self):
        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": []}
        _scan_all(mock_table, FilterExpression="test")
        mock_table.scan.assert_called_with(FilterExpression="test")


# ---------------------------------------------------------------------------
# _query_patches_for_image
# ---------------------------------------------------------------------------

class TestQueryPatches:
    def test_gsi_query(self):
        mock_table = MagicMock()
        mock_table.query.return_value = {
            "Items": [{"patch_id": "p1", "patch_path": "s3://b/p1.jpg"}]
        }
        result = _query_patches_for_image(mock_table, "img-123")
        assert len(result) == 1
        assert result[0]["patch_id"] == "p1"

    def test_falls_back_to_scan(self):
        mock_table = MagicMock()
        mock_table.query.side_effect = Exception("GSI not found")
        mock_table.scan.return_value = {
            "Items": [{"patch_id": "p2", "patch_path": "s3://b/p2.jpg"}]
        }
        result = _query_patches_for_image(mock_table, "img-456")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# PatchDataset (mocked construction)
# ---------------------------------------------------------------------------

class TestPatchDataset:
    @patch("src.apps.train.dataset.boto3")
    def test_build_index(self, mock_boto3):
        from src.apps.train.dataset import PatchDataset

        # Mock DynamoDB
        mock_ddb = MagicMock()
        mock_boto3.resource.return_value = mock_ddb
        mock_boto3.client.return_value = MagicMock()

        mock_img_table = MagicMock()
        mock_patch_table = MagicMock()
        mock_ddb.Table.side_effect = [mock_img_table, mock_patch_table]

        # Images scan returns 2 records
        mock_img_table.scan.return_value = {
            "Items": [
                {"image_id": "img1", "label": "authentic", "sublabel": "original", "split": "train"},
                {"image_id": "img2", "label": "inauthentic", "sublabel": "forgery", "split": "train"},
            ]
        }

        # Patches query
        mock_patch_table.query.side_effect = [
            {"Items": [{"patch_id": "p1", "patch_path": "s3://b/p1.jpg"}]},
            {"Items": [{"patch_id": "p2", "patch_path": "s3://b/p2.jpg"}]},
        ]

        ds = PatchDataset(
            img_table_name="images",
            patch_table_name="patches",
            processed_bucket="proc-bucket",
            region="us-east-1",
        )

        assert len(ds) == 2
        assert ds.authentic_count == 1
        assert ds.contrast_count == 1

    @patch("src.apps.train.dataset.boto3")
    def test_skips_records_without_label(self, mock_boto3):
        from src.apps.train.dataset import PatchDataset

        mock_ddb = MagicMock()
        mock_boto3.resource.return_value = mock_ddb
        mock_boto3.client.return_value = MagicMock()

        mock_img_table = MagicMock()
        mock_patch_table = MagicMock()
        mock_ddb.Table.side_effect = [mock_img_table, mock_patch_table]

        mock_img_table.scan.return_value = {
            "Items": [
                {"image_id": "img1"},  # no label
                {"image_id": "img2", "label": "authentic"},
            ]
        }
        mock_patch_table.query.return_value = {
            "Items": [{"patch_id": "p1", "patch_path": "s3://b/p1.jpg"}]
        }

        ds = PatchDataset(
            img_table_name="images",
            patch_table_name="patches",
            processed_bucket="bucket",
            region="us-east-1",
        )
        assert len(ds) == 1

    @patch("src.apps.train.dataset.boto3")
    def test_sublabel_counts(self, mock_boto3):
        from src.apps.train.dataset import PatchDataset

        mock_ddb = MagicMock()
        mock_boto3.resource.return_value = mock_ddb
        mock_boto3.client.return_value = MagicMock()

        mock_img_table = MagicMock()
        mock_patch_table = MagicMock()
        mock_ddb.Table.side_effect = [mock_img_table, mock_patch_table]

        mock_img_table.scan.return_value = {
            "Items": [
                {"image_id": "i1", "label": "authentic", "sublabel": "original"},
                {"image_id": "i2", "label": "inauthentic", "sublabel": "forgery"},
                {"image_id": "i3", "label": "inauthentic"},  # no sublabel
            ]
        }
        mock_patch_table.query.side_effect = [
            {"Items": [{"patch_id": "p1", "patch_path": "p1.jpg"}]},
            {"Items": [{"patch_id": "p2", "patch_path": "p2.jpg"}]},
            {"Items": [{"patch_id": "p3", "patch_path": "p3.jpg"}]},
        ]

        ds = PatchDataset(
            img_table_name="images",
            patch_table_name="patches",
            processed_bucket="bucket",
            region="us-east-1",
        )
        counts = ds.sublabel_counts
        assert counts["original"] == 1
        assert counts["forgery"] == 1
        assert counts["unlabelled"] == 1

    @patch("src.apps.train.dataset.boto3")
    def test_build_index_with_split_filter(self, mock_boto3):
        from src.apps.train.dataset import PatchDataset

        mock_ddb = MagicMock()
        mock_boto3.resource.return_value = mock_ddb
        mock_boto3.client.return_value = MagicMock()

        mock_img_table = MagicMock()
        mock_patch_table = MagicMock()
        mock_ddb.Table.side_effect = [mock_img_table, mock_patch_table]

        mock_img_table.scan.return_value = {
            "Items": [
                {"image_id": "img1", "label": "authentic", "split": "train"},
            ]
        }
        mock_patch_table.query.return_value = {
            "Items": [{"patch_id": "p1", "patch_path": "s3://b/p1.jpg"}]
        }

        ds = PatchDataset(
            img_table_name="images",
            patch_table_name="patches",
            processed_bucket="bucket",
            region="us-east-1",
            split="train",
        )
        assert len(ds) == 1
        # Split filtering happens in Python after scan (no DynamoDB FilterExpression).
        call_kwargs = mock_img_table.scan.call_args[1]
        assert "FilterExpression" not in call_kwargs
        assert "ProjectionExpression" in call_kwargs

    @patch("src.apps.train.dataset.boto3")
    def test_getitem(self, mock_boto3):
        from src.apps.train.dataset import PatchDataset

        mock_ddb = MagicMock()
        mock_s3 = MagicMock()
        mock_boto3.resource.return_value = mock_ddb
        mock_boto3.client.return_value = mock_s3

        mock_img_table = MagicMock()
        mock_patch_table = MagicMock()
        mock_ddb.Table.side_effect = [mock_img_table, mock_patch_table]

        mock_img_table.scan.return_value = {
            "Items": [{"image_id": "img1", "label": "authentic", "sublabel": "original"}]
        }
        mock_patch_table.query.return_value = {
            "Items": [{"patch_id": "p1", "patch_path": "s3://bucket/p1.jpg"}]
        }

        # Mock S3 download
        body = MagicMock()
        body.read.return_value = _make_test_image_bytes()
        mock_s3.get_object.return_value = {"Body": body}

        ds = PatchDataset(
            img_table_name="images",
            patch_table_name="patches",
            processed_bucket="bucket",
            region="us-east-1",
            transform=transforms.Compose([transforms.ToTensor()]),
        )

        img_tensor, label, weight, sublabel, path = ds[0]
        assert img_tensor.shape[0] == 3  # RGB channels
        assert label == 1
        assert weight == 1.0
        assert sublabel == "original"
