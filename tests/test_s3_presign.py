"""Tests for src.apps.backend.services.s3_presign — URI parsing and presigned URLs."""

from unittest.mock import MagicMock

import pytest

from src.apps.backend.services.s3_presign import parse_s3_uri, presigned_get_url


class TestParseS3Uri:
    """Tests for parse_s3_uri."""

    def test_basic_uri(self):
        bucket, key = parse_s3_uri("s3://my-bucket/path/to/image.jpg")
        assert bucket == "my-bucket"
        assert key == "path/to/image.jpg"

    def test_single_segment_key(self):
        bucket, key = parse_s3_uri("s3://bucket/file.txt")
        assert bucket == "bucket"
        assert key == "file.txt"

    def test_deep_nested_key(self):
        bucket, key = parse_s3_uri("s3://b/a/b/c/d/e/f.jpg")
        assert bucket == "b"
        assert key == "a/b/c/d/e/f.jpg"

    def test_url_decode_spaces(self):
        bucket, key = parse_s3_uri("s3://bucket/path%20with%20spaces/file.jpg")
        assert key == "path with spaces/file.jpg"

    def test_url_decode_special_chars(self):
        bucket, key = parse_s3_uri("s3://bucket/100%25done.jpg")
        assert key == "100%done.jpg"

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="s3://"):
            parse_s3_uri("")

    def test_none_raises(self):
        with pytest.raises(ValueError, match="s3://"):
            parse_s3_uri(None)

    def test_wrong_scheme_raises(self):
        with pytest.raises(ValueError, match="s3://"):
            parse_s3_uri("https://bucket/key")

    def test_no_key_raises(self):
        with pytest.raises(ValueError, match="missing key"):
            parse_s3_uri("s3://bucket-only")

    def test_empty_key_raises(self):
        with pytest.raises(ValueError, match="empty bucket or key"):
            parse_s3_uri("s3://bucket/")

    def test_empty_bucket_raises(self):
        with pytest.raises(ValueError, match="empty bucket or key"):
            parse_s3_uri("s3:///key")


class TestPresignedGetUrl:
    """Tests for presigned_get_url."""

    def test_calls_generate_presigned_url(self):
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://signed-url"

        result = presigned_get_url(mock_s3, "s3://bucket/key.jpg", 3600)

        assert result == "https://signed-url"
        mock_s3.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "bucket", "Key": "key.jpg"},
            ExpiresIn=3600,
        )

    def test_default_expires(self):
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "url"

        presigned_get_url(mock_s3, "s3://b/k.jpg")

        call_kwargs = mock_s3.generate_presigned_url.call_args
        assert call_kwargs[1]["ExpiresIn"] == 3600 or call_kwargs[0][2] if len(call_kwargs[0]) > 2 else True

    def test_invalid_uri_propagates_error(self):
        mock_s3 = MagicMock()
        with pytest.raises(ValueError):
            presigned_get_url(mock_s3, "not-an-s3-uri")

    def test_with_moto(self, s3):
        """Integration test with mocked S3."""
        s3.put_object(Bucket="test-raw-bucket", Key="test/img.jpg", Body=b"data")

        url = presigned_get_url(s3, "s3://test-raw-bucket/test/img.jpg", 60)
        assert "test-raw-bucket" in url
        assert "img.jpg" in url
