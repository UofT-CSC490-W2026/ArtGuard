"""Parse s3:// URIs and build presigned GET URLs for browser access."""

from __future__ import annotations

from urllib.parse import unquote


def parse_s3_uri(uri: str) -> tuple[str, str]:
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
    bucket, key = parse_s3_uri(uri)
    return s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in,
    )
