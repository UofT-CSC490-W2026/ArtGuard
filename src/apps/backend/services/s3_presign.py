"""S3 presigned URL utilities for browser-accessible image downloads.

Parses ``s3://`` URIs and generates time-limited presigned GET URLs
so the frontend can display images stored in private S3 buckets.
"""

from __future__ import annotations

from urllib.parse import unquote


def parse_s3_uri(uri: str) -> tuple[str, str]:
    """Parse an ``s3://bucket/key`` URI into its (bucket, key) components.

    The key portion is URL-decoded to handle percent-encoded characters.

    >>> parse_s3_uri("s3://my-bucket/path/to/image.jpg")
    ('my-bucket', 'path/to/image.jpg')
    >>> parse_s3_uri("s3://my-bucket/path%20with%20spaces/file.jpg")
    ('my-bucket', 'path with spaces/file.jpg')

    Raises:
        ValueError: If uri is empty, does not start with ``s3://``, or is
                    missing the bucket or key component.
    """
    if not uri or not uri.startswith("s3://"):
        raise ValueError("image_path must be an s3:// URI")
    rest = uri[5:]
    if "/" not in rest:
        raise ValueError("invalid s3 URI (missing key)")
    bucket, key = rest.split("/", 1)
    if not bucket or not key:
        raise ValueError("invalid s3 URI (empty bucket or key)")
    return bucket, unquote(key)


def presigned_get_url(s3_client, uri: str, expires_in: int = 3600) -> str:
    """Generate a presigned GET URL for an S3 object identified by its s3:// URI.

    >>> presigned_get_url(mock_s3, "s3://bucket/key.jpg", 3600)  # doctest: +SKIP
    'https://bucket.s3.amazonaws.com/key.jpg?...'

    Args:
        s3_client:  A boto3 S3 client instance.
        uri:        An ``s3://bucket/key`` URI pointing to the object.
        expires_in: URL validity duration in seconds (default 3600 = 1 hour).

    Returns:
        A presigned HTTPS URL string.
    """
    bucket, key = parse_s3_uri(uri)
    return s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in,
    )
