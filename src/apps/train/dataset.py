"""
dataset.py — Patch dataset for art authentication training.

Data flow:
  1. Scan DynamoDB Images table  → collect {image_id, label, sublabel} for all records
  2. Query DynamoDB Patches table → collect {patch_id, patch_path} per image
  3. On __getitem__              → stream patch bytes from S3 via boto3

DynamoDB schema assumed (matches schemas.py):
  Images  table PK: image_id  (str)
    - label    : "authentic" | "inauthentic"   (binary classification target)
    - sublabel : "original"  | "forgery" | "imitation" | "proxy"  (fine-grained group)
    - split    : "train" | "val" | "test" | "unassigned"
  Patches table PK: patch_id  (str)
    - image_id  : str
    - patch_path: bare S3 key (e.g. "training/{image_id}/x0_y0_downsample_orig.jpg")

Label convention:
  1 → authentic
  0 → inauthentic (forgery / imitation / proxy)
"""

from __future__ import annotations

from io import BytesIO
from typing import Optional

import boto3
from boto3.dynamodb.conditions import Attr, Key
from PIL import Image
from torch.utils.data import Dataset
from torchvision import transforms

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD  = [0.229, 0.224, 0.225]

def default_train_transforms() -> transforms.Compose:
    # Patches are already 224x224 from preprocess.py (TARGET_PATCH_SIZE=224)
    # so no resize needed — just augment, tensorise, and normalise.
    return transforms.Compose([
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])

def default_val_transforms() -> transforms.Compose:
    return transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])


def _s3_path_to_bucket_key(s3_path: str) -> tuple[str, str]:
    """'s3://bucket/a/b/c.png' → ('bucket', 'a/b/c.png')"""
    assert s3_path.startswith("s3://"), f"Expected s3:// path, got: {s3_path}"
    without_scheme = s3_path[5:]
    bucket, _, key = without_scheme.partition("/")
    return bucket, key


def _stream_patch_from_s3(s3_client, patch_path: str, fallback_bucket: str = "") -> Image.Image:
    """
    Fetch a patch from S3. Handles two path formats:
      - Full URI:  s3://bucket/key
      - Bare key:  training/img123/x0_y0_downsample_orig.jpg  (from build_patch_s3_key)

    For bare keys, fallback_bucket must be supplied (your processed S3 bucket).
    """
    if patch_path.startswith("s3://"):
        bucket, key = _s3_path_to_bucket_key(patch_path)
    else:
        assert fallback_bucket, "fallback_bucket required for bare S3 key paths"
        bucket, key = fallback_bucket, patch_path

    resp = s3_client.get_object(Bucket=bucket, Key=key)
    img_bytes = resp["Body"].read()
    return Image.open(BytesIO(img_bytes)).convert("RGB")


def _scan_all(table, **kwargs) -> list[dict]:
    """Paginate through a full table scan, returning all items."""
    items: list[dict] = []
    resp = table.scan(**kwargs)
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **kwargs)
        items.extend(resp.get("Items", []))
    return items


def _query_patches_for_image(patch_table, image_id: str) -> list[dict]:
    """
    Query the Patches table by image_id using a GSI named 'image_id-index'.
    Falls back to a full scan with filter if the GSI doesn't exist (dev only).
    """
    try:
        resp = patch_table.query(
            IndexName="image_id-index",
            KeyConditionExpression=Key("image_id").eq(image_id),
            ProjectionExpression="patch_id, patch_path",
        )
        return resp.get("Items", [])
    except Exception:
        return _scan_all(
            patch_table,
            FilterExpression=Key("image_id").eq(image_id),
            ProjectionExpression="patch_id, patch_path",
        )


# ---------------------------------------------------------------------------
# Sample type
# ---------------------------------------------------------------------------
# Each entry in _samples is:
#   (patch_path, label, weight, sublabel, image_id)
#
#   patch_path : bare S3 key
#   label      : 1 = authentic, 0 = inauthentic
#   weight     : imitation_weight for inauthentic, 1.0 for authentic
#   sublabel   : "original" | "forgery" | "imitation" | "proxy" | None
#   image_id   : str  (used for painting-level aggregation in evaluate.py)

Sample = tuple[str, int, float, Optional[str], str]


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

class PatchDataset(Dataset):
    """
    Streams 224×224 patches from S3, labelled via DynamoDB ImageRecord.

    Each __getitem__ returns:
        (image_tensor, label, weight, sublabel, patch_path)

    sublabel and patch_path are passed through so evaluate.py can produce
    per-sublabel metric breakdowns and a full per-patch prediction log
    without any extra DynamoDB lookups.

    Args:
        img_table_name   : DynamoDB Images table name
        patch_table_name : DynamoDB Patches table name
        processed_bucket : S3 bucket where patches live
        region           : AWS region
        transform        : torchvision transform applied to each patch
        imitation_weight : Per-sample weight for inauthentic patches (paper wim=10)
        split            : "train" | "val" | "test" | None (all records)
    """

    def __init__(
        self,
        img_table_name: str,
        patch_table_name: str,
        processed_bucket: str,
        region: str,
        transform: Optional[transforms.Compose] = None,
        imitation_weight: float = 10.0,
        split: Optional[str] = None,
    ) -> None:
        self.transform        = transform or default_train_transforms()
        self.imitation_weight = imitation_weight
        self.processed_bucket = processed_bucket
        self.split            = split

        self._s3    = boto3.client("s3", region_name=region)
        ddb         = boto3.resource("dynamodb", region_name=region)
        img_table   = ddb.Table(img_table_name)
        patch_table = ddb.Table(patch_table_name)

        self._samples: list[Sample] = []
        self._build_index(img_table, patch_table)

    def _build_index(self, img_table, patch_table) -> None:
        split_msg = f" (split='{self.split}')" if self.split else " (all splits)"
        print(f"Building dataset index from DynamoDB{split_msg}...")

        scan_kwargs: dict = dict(
            ProjectionExpression="image_id, #lb, #sl, #sp",
            ExpressionAttributeNames={
                "#lb": "label",
                "#sl": "sublabel",
                "#sp": "split",
            },
        )
        if self.split:
            scan_kwargs["FilterExpression"] = Attr("split").eq(self.split)

        image_records = _scan_all(img_table, **scan_kwargs)

        skipped = 0
        for rec in image_records:
            if "label" not in rec:
                skipped += 1
                continue

            # schemas.py stores label as str: "authentic" | "inauthentic"
            label    = 1 if rec["label"] == "authentic" else 0
            weight   = 1.0 if label == 1 else self.imitation_weight
            sublabel = rec.get("sublabel", None)
            image_id = rec["image_id"]

            patches = _query_patches_for_image(patch_table, image_id)
            for p in patches:
                self._samples.append((
                    p["patch_path"],
                    label,
                    weight,
                    sublabel,
                    image_id,
                ))

        print(
            f"Index built: {len(self._samples):,} patches "
            f"({sum(1 for s in self._samples if s[1]==1):,} authentic, "
            f"{sum(1 for s in self._samples if s[1]==0):,} inauthentic). "
            f"Skipped {skipped} records with no label."
        )

    def __len__(self) -> int:
        return len(self._samples)

    def __getitem__(self, idx: int):
        patch_path, label, weight, sublabel, image_id = self._samples[idx]
        img = _stream_patch_from_s3(self._s3, patch_path, fallback_bucket=self.processed_bucket)
        if self.transform:
            img = self.transform(img)
        # sublabel and patch_path returned as strings so DataLoader can collate
        # without a custom collate_fn (empty string used in place of None)
        return img, label, weight, sublabel or "", patch_path

    # ------------------------------------------------------------------
    @property
    def authentic_count(self) -> int:
        return sum(1 for s in self._samples if s[1] == 1)

    @property
    def contrast_count(self) -> int:
        return sum(1 for s in self._samples if s[1] == 0)

    @property
    def sublabel_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for s in self._samples:
            sl = s[3] or "unlabelled"
            counts[sl] = counts.get(sl, 0) + 1
        return counts