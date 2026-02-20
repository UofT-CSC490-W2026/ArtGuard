# model/cross_validation.py
import argparse
import os
import time
import uuid
from typing import Dict, List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr

from PIL import Image
from io import BytesIO
from preprocessing.split import assign_folds  
from preprocessing.process import process_training_image  

def now_ms() -> int:
    """
    This function provides the current time, in ms.
    """
    return int(time.time() * 1000)

def parse_args() -> argparse.Namespace:
    """
    This function will parse the arguments passed from backend endpoint, and provide
    them as metadata for the training run.
    """
    p = argparse.ArgumentParser(description="ArtGuard cross-validation driver")
    p.add_argument("--run_id", required=True)
    p.add_argument("--dataset_version", required=True)
    p.add_argument("--k_folds", type=int, default=5)
    p.add_argument("--outer_split_seed", type=int, default=17)
    p.add_argument("--inner_split_seed", type=int, default=99)
    return p.parse_args()


def scan_images_by_dataset_version(img_table, dataset_version: str) -> List[dict]:
    """
    Return all ImageRecords that use the given dataset version.
    """
    # TODO: Make dataset_version a GSI so we do not have to use scan and query.
    items: List[dict] = []
    kwargs = {
        "FilterExpression": Attr("dataset_version").eq(dataset_version)
    }
    while True:
        resp = img_table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    return items


def update_image_fold_assignment(
    img_table,
    image_id: str,
    run_id: str,
    fold_id: int,
    dataset_version: Optional[str] = None,
) -> None:
    """
    Update each ImageRecord's metadata after fold assignment, including dataset version,
    run_id and fold_id.
    """
    if dataset_version is not None:
        img_table.update_item(
            Key={"image_id": image_id},
            UpdateExpression="SET #rid = :rid, #fid = :fid, #dv = :dv",
            ExpressionAttributeNames={
                "#rid": "run_id",
                "#fid": "fold_id",
                "#dv": "dataset_version",
            },
            ExpressionAttributeValues={
                ":rid": run_id,
                ":fid": int(fold_id),
                ":dv": dataset_version,
            },
        )
    else:
        img_table.update_item(
            Key={"image_id": image_id},
            UpdateExpression="SET #rid = :rid, #fid = :fid",
            ExpressionAttributeNames={"#rid": "run_id", "#fid": "fold_id"},
            ExpressionAttributeValues={":rid": run_id, ":fid": int(fold_id)},
        )


def format_s3_uri(s3_uri: str) -> Tuple[str, str]:
    """
    Formats S3 uri (s3://artguard-images-raw-dev/training/raw/abc123/image.jpg")
    into Bucket, Key format for easy access:
    bucket = "artguard-images-raw-dev"
    key = "training/raw/abc123/image.jpg"
    """
    rest = s3_uri[len("s3://"):]
    bucket, _, key = rest.partition("/")
    return bucket, key

def download(s3_client, bucket: str, key: str) -> bytes:
    """
    Given an image stored in S3, it downloads the image for processing.
    """
    resp = s3_client.get_object(Bucket=bucket, Key=key)
    return resp["Body"].read()

def write_patch_records(patch_table, image_id: str, patches: List[dict], created_at: int) -> None:
    """
    Write each patch's metadata in DynamoDB.
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


def main() -> None:
    args = parse_args()

    run_id: str = args.run_id
    dataset_version: str = args.dataset_version
    k_folds: int = args.k_folds
    outer_seed: int = args.outer_split_seed
    inner_seed: int = args.inner_split_seed  

    # TODO: Configuration 
    region = os.getenv("AWS_REGION")
    raw_bucket = os.getenv("S3_IMAGES_RAW_BUCKET")
    processed_bucket = os.getenv("S3_IMAGES_PROCESSED_BUCKET")
    raw_prefix = os.getenv("S3_RAW_TRAIN_PREFIX", "training/raw").strip().strip("/")
    processed_prefix = os.getenv("S3_PROCESSED_TRAIN_PREFIX", "training/processed").strip().strip("/")

    img_table_name = os.getenv("DDB_IMAGES_TABLE")
    patch_table_name = os.getenv("DDB_PATCHES_TABLE")

    s3 = boto3.client("s3", region_name=region)
    ddb = boto3.resource("dynamodb", region_name=region)
    img_table = ddb.Table(img_table_name)
    patch_table = ddb.Table(patch_table_name)

    # Retrieve all the images.
    items = scan_images_by_dataset_version(img_table, dataset_version)
    # Split the images into different folds using stratified k-fold cross validation.
    assignment = assign_folds(items, k_folds=k_folds, outer_seed=outer_seed, inner_seed=inner_seed, stratify_on="sublabel")
    
    # Persist image assignment metadata to DynamoDB.
    for image_id, fold_id in assignment.items():
        update_image_fold_assignment(img_table, image_id=image_id, run_id=run_id, fold_id=fold_id, dataset_version=dataset_version)

    # Process the images.
    created_at = now_ms()
    processed_count = 0

    for item in items:
        image_id = item["image_id"]
        image_path = item.get("image_path")  
   
        # Download image bytes.
        bucket, key = format_s3_uri(image_path)
        img_bytes = download(s3, bucket, key)
        pil_img = Image.open(BytesIO(img_bytes)).convert("RGB")

        # Break the image down into patches.
        patches = process_training_image(
            img=pil_img, 
            image_id=image_id,
            processed_bucket=processed_bucket, 
            processed_prefix=processed_prefix,
            s3_client=s3
        )

        # Update the patches' metadata in DynamoDB.
        write_patch_records(patch_table, image_id=image_id, patches=patches, created_at=created_at)
        processed_count += 1

    # TODO: Train the model.
    # TODO: Consolidate results.


if __name__ == "__main__":
    main()