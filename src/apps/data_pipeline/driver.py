"""
Data processing driver -- runs as a standalone Fargate task.

Reads raw images from s3://{RAW_BUCKET}/training/unprocessed/,
processes each into 256x256 patches (center-square + grid),
uploads patches to s3://{PROCESSED_BUCKET}/training/{image_id}/,
writes metadata to DynamoDB, and moves the original to
s3://{RAW_BUCKET}/training/processed/.

Usage (called via ECS container override from /process_data endpoint):
    python -m src.apps.data_pipeline.driver --run_id <uuid>
"""
from __future__ import annotations

import argparse
import os
import time
import uuid
from typing import List, Optional

import boto3
from PIL import Image
from io import BytesIO

from src.apps.data_pipeline.process import process_image_to_patches

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}

# S3 prefix layout:
#   Raw bucket:       training/unprocessed/, training/processed/, inference/
#   Processed bucket: training/, inference/
RAW_PREFIX = "training/unprocessed/"
RAW_DONE_PREFIX = "training/processed/"
PROCESSED_PREFIX = "training"


def now_ms() -> int:
    return int(time.time() * 1000)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ArtGuard data processing driver")
    p.add_argument("--run_id", required=True)
    return p.parse_args()


def list_unprocessed_keys(s3_client, bucket: str, prefix: str) -> List[str]:
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
    """
    Try to extract an existing image_id from the key structure.
    Expected: training/unprocessed/{image_id}/{filename}
    Returns the image_id if the key has 4+ segments, None otherwise.
    """
    parts = key.split("/")
    # parts[0] = "training", parts[1] = "unprocessed", parts[2] = image_id, parts[3] = filename
    if len(parts) >= 4 and parts[2]:
        return parts[2]
    return None


def image_record_exists(img_table, image_id: str) -> bool:
    """Check if an ImageRecord already exists in DynamoDB."""
    resp = img_table.get_item(Key={"image_id": image_id}, ProjectionExpression="image_id")
    return "Item" in resp


def download(s3_client, bucket: str, key: str) -> bytes:
    resp = s3_client.get_object(Bucket=bucket, Key=key)
    return resp["Body"].read()


def write_patch_records(
    patch_table, image_id: str, patches: List[dict], created_at: int
) -> None:
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
    """Move from training/unprocessed/ to training/processed/ in the raw bucket."""
    dest_key = key.replace("training/unprocessed/", "training/processed/", 1)
    s3_client.copy_object(
        Bucket=bucket,
        CopySource={"Bucket": bucket, "Key": key},
        Key=dest_key,
    )
    s3_client.delete_object(Bucket=bucket, Key=key)


def process_single_image(
    s3_client,
    img_table,
    patch_table,
    raw_bucket: str,
    processed_bucket: str,
    key: str,
    run_id: str,
) -> int:
    """Process one image from S3. Returns the number of patches created."""
    img_bytes = download(s3_client, raw_bucket, key)

    try:
        img = Image.open(BytesIO(img_bytes)).convert("RGB")
    except Exception as exc:
        print(f"  SKIP (not a valid image): {exc}")
        return 0

    w, h = img.size
    created_at = now_ms()
    filename = os.path.basename(key)

    # Use existing image_id from key path (training/unprocessed/{image_id}/{filename})
    # or generate a new one for flat-structure uploads
    existing_id = extract_image_id(key)
    if existing_id:
        image_id = existing_id
    else:
        image_id = str(uuid.uuid4())

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
        # Update existing record with run_id
        img_table.update_item(
            Key={"image_id": image_id},
            UpdateExpression="SET run_id = :r",
            ExpressionAttributeValues={":r": run_id},
        )

    write_patch_records(patch_table, image_id=image_id, patches=patches, created_at=created_at)

    # Move original from training/unprocessed/ to training/processed/ in the raw bucket
    move_to_processed(s3_client, raw_bucket, key)

    return len(patches)


def main() -> None:
    args = parse_args()
    run_id = args.run_id

    region = os.getenv("AWS_REGION")
    raw_bucket = os.getenv("S3_IMAGES_RAW_BUCKET")
    processed_bucket = os.getenv("S3_IMAGES_PROCESSED_BUCKET")
    img_table_name = os.getenv("DDB_IMAGES_TABLE")
    patch_table_name = os.getenv("DDB_PATCHES_TABLE")
    runs_table_name = os.getenv("DDB_RUNS_TABLE")

    s3 = boto3.client("s3", region_name=region)
    ddb = boto3.resource("dynamodb", region_name=region)
    img_table = ddb.Table(img_table_name)
    patch_table = ddb.Table(patch_table_name)
    runs_table = ddb.Table(runs_table_name)

    # Record run as started
    runs_table.put_item(Item={
        "run_id": run_id,
        "created_at": now_ms(),
        "status": "running",
    })

    keys = list_unprocessed_keys(s3, raw_bucket, RAW_PREFIX)
    total = len(keys)
    print(f"Found {total} images in s3://{raw_bucket}/{RAW_PREFIX}")

    total_patches = 0
    errors = 0

    for i, key in enumerate(keys, 1):
        print(f"[{i}/{total}] Processing {key}")
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
            print(f"  -> {n} patches created")
        except Exception as exc:
            errors += 1
            print(f"  ERROR: {exc}")

    # Update run record with final status
    status = "completed" if errors == 0 else "completed_with_errors"
    runs_table.update_item(
        Key={"run_id": run_id},
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": status},
    )

    print(f"\nDone. Images: {total}, Patches: {total_patches}, Errors: {errors}")


if __name__ == "__main__":
    main()
