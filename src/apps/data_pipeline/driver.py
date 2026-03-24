"""Data processing driver -- runs as a standalone ECS Fargate task.

Reads raw images from ``s3://{RAW_BUCKET}/training/unprocessed/``,
processes each into 224x224 patches (center-crop + downsample per grid cell),
uploads patches to ``s3://{PROCESSED_BUCKET}/training/{image_id}/``,
writes metadata to DynamoDB, and moves the original to
``s3://{RAW_BUCKET}/training/processed/``.

Usage (called via ECS container override from the /process_data endpoint)::

    python -m src.apps.data_pipeline.driver --run_id <uuid>
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import uuid
from io import BytesIO
from typing import List, Optional

import boto3
from PIL import Image

from src.apps.data_pipeline.preprocess import process_image_to_patches

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
"""File extensions recognised as images during S3 listing."""

# S3 prefix layout:
#   Raw bucket:       training/unprocessed/, training/processed/, inference/
#   Processed bucket: training/, inference/
RAW_PREFIX = "training/unprocessed/"
RAW_DONE_PREFIX = "training/processed/"
PROCESSED_PREFIX = "training"


def now_ms() -> int:
    """Return the current time as Unix milliseconds.

    >>> isinstance(now_ms(), int)
    True
    """
    return int(time.time() * 1000)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the data processing driver.

    Returns:
        Namespace with a ``run_id`` attribute (required UUID string).
    """
    p = argparse.ArgumentParser(description="ArtGuard data processing driver")
    p.add_argument("--run_id", required=True)
    return p.parse_args()


def list_unprocessed_keys(s3_client, bucket: str, prefix: str) -> List[str]:
    """List all image S3 keys under the given prefix.

    Paginates through the S3 ListObjectsV2 response and filters for
    keys whose file extension matches IMAGE_EXTENSIONS.

    Args:
        s3_client: A boto3 S3 client.
        bucket:    S3 bucket name to list.
        prefix:    S3 key prefix to filter (e.g. ``"training/unprocessed/"``).

    Returns:
        A list of S3 object keys for image files.
    """
    keys: List[str] = []
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            ext = os.path.splitext(key)[1].lower()
            if ext in IMAGE_EXTENSIONS:
                keys.append(key)
    return keys


def extract_image_id(key: str) -> Optional[str]:
    """Extract the image_id from an S3 key with the expected structure.

    Expected format: ``training/unprocessed/{image_id}/{filename}``.
    Returns the image_id segment if the key has 4+ path segments, or
    None for flat-structure keys.

    >>> extract_image_id("training/unprocessed/abc-123/photo.jpg")
    'abc-123'
    >>> extract_image_id("training/unprocessed/photo.jpg") is None
    True
    """
    parts = key.split("/")
    if len(parts) >= 4 and parts[2]:
        return parts[2]
    return None


def image_record_exists(img_table, image_id: str) -> bool:
    """Check whether an ImageRecord already exists in DynamoDB for this image_id.

    Args:
        img_table: A boto3 DynamoDB Table resource.
        image_id:  The image UUID to look up.

    Returns:
        True if a record with this image_id exists.
    """
    resp = img_table.get_item(Key={"image_id": image_id}, ProjectionExpression="image_id")
    return "Item" in resp


def download(s3_client, bucket: str, key: str) -> bytes:
    """Download an object from S3 and return its raw bytes.

    Args:
        s3_client: A boto3 S3 client.
        bucket:    S3 bucket name.
        key:       S3 object key.

    Returns:
        The full object body as bytes.

    Raises:
        IOError: If the S3 object cannot be downloaded.
    """
    try:
        resp = s3_client.get_object(Bucket=bucket, Key=key)
        return resp["Body"].read()
    except Exception as exc:
        raise IOError(f"Failed to download s3://{bucket}/{key}: {exc}") from exc


def write_patch_records(
    patch_table, image_id: str, patches: List[dict], created_at: int
) -> None:
    """Write a list of patch metadata dicts to the DynamoDB patches table.

    Each dict in patches must contain ``patch_id``, ``patch_type``,
    ``patch_path``, and bounding box fields (``patch_x``, ``patch_y``,
    ``patch_width``, ``patch_height``).

    Args:
        patch_table: A boto3 DynamoDB Table resource.
        image_id:    Parent image UUID.
        patches:     List of patch metadata dicts from ``process_image_to_patches``.
        created_at:  Unix timestamp in milliseconds.
    """
    for p in patches:
        patch_table.put_item(Item={
            "patch_id": p["patch_id"],
            "image_id": image_id,
            "patch_type": p["patch_type"],
            "patch_path": p["patch_path"],
            "patch_x": int(p["patch_x"]),
            "patch_y": int(p["patch_y"]),
            "patch_width": int(p["patch_width"]),
            "patch_height": int(p["patch_height"]),
            "created_at": int(created_at),
        })


def move_to_processed(s3_client, bucket: str, key: str) -> None:
    """Move an S3 object from training/unprocessed/ to training/processed/.

    Performs a server-side copy followed by a delete of the original key.

    Args:
        s3_client: A boto3 S3 client.
        bucket:    S3 bucket name (source and destination are the same bucket).
        key:       S3 object key under training/unprocessed/.

    Raises:
        IOError: If the copy or delete operation fails.
    """
    dest_key = key.replace("training/unprocessed/", "training/processed/", 1)
    try:
        s3_client.copy_object(
            Bucket=bucket,
            CopySource={"Bucket": bucket, "Key": key},
            Key=dest_key,
            ServerSideEncryption="AES256",
        )
        s3_client.delete_object(Bucket=bucket, Key=key)
    except Exception as exc:
        raise IOError(
            f"Failed to move s3://{bucket}/{key} to {dest_key}: {exc}"
        ) from exc


def process_single_image(
    s3_client,
    img_table,
    patch_table,
    raw_bucket: str,
    processed_bucket: str,
    key: str,
    run_id: str,
) -> int:
    """Download, patch, and catalogue one image from S3.

    Downloads the image, splits it into patches via ``process_image_to_patches``,
    writes metadata to DynamoDB, and moves the original to the processed prefix.

    Args:
        s3_client:        A boto3 S3 client.
        img_table:        DynamoDB Table for image records.
        patch_table:      DynamoDB Table for patch records.
        raw_bucket:       S3 bucket containing raw images.
        processed_bucket: S3 bucket for processed patches.
        key:              S3 object key of the image to process.
        run_id:           UUID of the current processing run.

    Returns:
        The number of patches created (0 if the file is not a valid image).
    """
    img_bytes = download(s3_client, raw_bucket, key)

    try:
        img = Image.open(BytesIO(img_bytes)).convert("RGB")
    except Exception as exc:
        logger.warning("Skipping invalid image %s: %s", key, exc)
        return 0

    w, h = img.size
    created_at = now_ms()
    filename = os.path.basename(key)

    existing_id = extract_image_id(key)
    image_id = existing_id if existing_id else str(uuid.uuid4())

    patches = process_image_to_patches(
        img=img,
        image_id=image_id,
        processed_bucket=processed_bucket,
        processed_prefix=PROCESSED_PREFIX,
        s3_client=s3_client,
    )

    # Only create ImageRecord if one doesn't already exist (the upload script
    # may have already written it with label/sublabel metadata from the CSV).
    if not image_record_exists(img_table, image_id):
        img_table.put_item(Item={
            "image_id": image_id,
            "created_at": created_at,
            "image_name": filename,
            "image_path": f"s3://{raw_bucket}/{key}",
            "image_width": w,
            "image_height": h,
            "run_id": run_id,
        })
    else:
        img_table.update_item(
            Key={"image_id": image_id},
            UpdateExpression="SET run_id = :r",
            ExpressionAttributeValues={":r": run_id},
        )

    write_patch_records(patch_table, image_id=image_id, patches=patches, created_at=created_at)
    move_to_processed(s3_client, raw_bucket, key)

    return len(patches)


def _require_env(name: str) -> str:
    """Read a required environment variable, raising if it is not set.

    Args:
        name: The environment variable name.

    Returns:
        The environment variable value.

    Raises:
        EnvironmentError: If the variable is not set or empty.
    """
    value = os.getenv(name, "").strip()
    if not value:
        raise EnvironmentError(f"Required environment variable {name} is not set")
    return value


def _setup_pipeline_logging() -> None:
    """Configure JSON structured logging for the standalone pipeline task.

    Uses the same JSON format as the backend so CloudWatch Logs Insights
    queries work identically across both log groups.
    """
    from src.apps.backend.logging_config import JSONFormatter

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)

    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)


def main() -> None:
    """Entry point for the ECS Fargate data processing task.

    Reads configuration from environment variables, lists unprocessed images
    in S3, processes each one into patches, and updates the run status in
    DynamoDB when complete.

    Raises:
        EnvironmentError: If any required environment variable is missing.
    """
    _setup_pipeline_logging()

    args = parse_args()
    run_id = args.run_id

    logger.info("Data pipeline starting", extra={"run_id": run_id})

    region = _require_env("AWS_REGION")
    raw_bucket = _require_env("S3_IMAGES_RAW_BUCKET")
    processed_bucket = _require_env("S3_IMAGES_PROCESSED_BUCKET")
    img_table_name = _require_env("DDB_IMAGES_TABLE")
    patch_table_name = _require_env("DDB_PATCHES_TABLE")
    runs_table_name = _require_env("DDB_RUNS_TABLE")

    s3 = boto3.client("s3", region_name=region)
    ddb = boto3.resource("dynamodb", region_name=region)
    img_table = ddb.Table(img_table_name)
    patch_table = ddb.Table(patch_table_name)
    runs_table = ddb.Table(runs_table_name)

    runs_table.put_item(Item={
        "run_id": run_id,
        "created_at": now_ms(),
        "status": "running",
    })

    keys = list_unprocessed_keys(s3, raw_bucket, RAW_PREFIX)
    total = len(keys)
    logger.info("Found %d images in s3://%s/%s", total, raw_bucket, RAW_PREFIX)

    total_patches = 0
    errors = 0
    start_time = time.perf_counter()

    for i, key in enumerate(keys, 1):
        logger.info("[%d/%d] Processing %s", i, total, key)
        try:
            n = process_single_image(
                s3_client=s3,
                img_table=img_table,
                patch_table=patch_table,
                raw_bucket=raw_bucket,
                processed_bucket=processed_bucket,
                key=key,
                run_id=run_id,
            )
            total_patches += n
            logger.info("Created %d patches for %s", n, key)
        except Exception as exc:
            errors += 1
            logger.error("Failed to process %s: %s", key, exc, exc_info=True)

    final_status = "completed" if errors == 0 else "completed_with_errors"
    runs_table.update_item(
        Key={"run_id": run_id},
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": final_status},
    )

    duration = time.perf_counter() - start_time
    logger.info(
        "Pipeline finished: images=%d patches=%d errors=%d status=%s duration=%.1fs",
        total, total_patches, errors, final_status, duration,
    )


if __name__ == "__main__":
    main()
