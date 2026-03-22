"""PyTorch Dataset for streaming art authentication patches from S3.

Data flow:
  1. Scan DynamoDB Images table  -> collect {image_id, label, sublabel} for all records
  2. Query DynamoDB Patches table -> collect {patch_id, patch_path} per image
  3. On ``__getitem__``           -> stream patch bytes from S3 via boto3

DynamoDB schema assumed (matches schemas.py):

  **Images table** (PK: image_id):
    - label    : ``"authentic"`` | ``"inauthentic"``
    - sublabel : ``"original"`` | ``"forgery"`` | ``"imitation"`` | ``"proxy"``
    - split    : ``"train"`` | ``"val"`` | ``"test"`` | ``"unassigned"``

  **Patches table** (PK: patch_id):
    - image_id  : str
    - patch_path : S3 URI or bare key

Label convention:
  - 1 -> authentic
  - 0 -> inauthentic (forgery / imitation / proxy)
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Optional

import boto3
from boto3.dynamodb.conditions import Attr, Key
from PIL import Image
from torch.utils.data import Dataset
from torchvision import transforms

logger = logging.getLogger(__name__)

IMAGENET_MEAN = [0.485, 0.456, 0.406]
"""ImageNet channel means for normalisation."""

IMAGENET_STD = [0.229, 0.224, 0.225]
"""ImageNet channel standard deviations for normalisation."""


def default_train_transforms() -> transforms.Compose:
    """Return the default training transform pipeline.

    Patches are already 224x224 from preprocess.py, so no resize is needed.
    Applies random horizontal flip, tensor conversion, and ImageNet normalisation.

    >>> t = default_train_transforms()
    >>> isinstance(t, transforms.Compose)
    True
    """
    return transforms.Compose([
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])


def default_val_transforms() -> transforms.Compose:
    """Return the default validation/test transform pipeline.

    Converts to tensor and applies ImageNet normalisation (no augmentation).

    >>> t = default_val_transforms()
    >>> isinstance(t, transforms.Compose)
    True
    """
    return transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])


def _s3_path_to_bucket_key(s3_path: str) -> tuple[str, str]:
    """Parse an s3:// URI into (bucket, key) components.

    >>> _s3_path_to_bucket_key("s3://my-bucket/path/to/file.png")
    ('my-bucket', 'path/to/file.png')

    Args:
        s3_path: An ``s3://bucket/key`` URI string.

    Returns:
        A (bucket, key) tuple.
    """
    if not s3_path.startswith("s3://"):
        raise ValueError(f"Expected s3:// path, got: {s3_path}")
    without_scheme = s3_path[5:]
    bucket, _, key = without_scheme.partition("/")
    return bucket, key


def _stream_patch_from_s3(
    s3_client, patch_path: str, fallback_bucket: str = ""
) -> Image.Image:
    """Download a patch image from S3 and return it as a PIL RGB Image.

    Handles two path formats:
      - Full URI:  ``s3://bucket/key``
      - Bare key:  ``training/img123/x0_y0_downsample_orig.jpg``

    For bare keys, fallback_bucket must be supplied (your processed S3 bucket).

    Args:
        s3_client:       A boto3 S3 client.
        patch_path:      S3 URI or bare key for the patch.
        fallback_bucket: Bucket name to use when patch_path is a bare key.

    Returns:
        A PIL Image in RGB mode.
    """
    if patch_path.startswith("s3://"):
        bucket, key = _s3_path_to_bucket_key(patch_path)
    else:
        if not fallback_bucket:
            raise ValueError("fallback_bucket required for bare S3 key paths")
        bucket, key = fallback_bucket, patch_path

    try:
        resp = s3_client.get_object(Bucket=bucket, Key=key)
        img_bytes = resp["Body"].read()
        return Image.open(BytesIO(img_bytes)).convert("RGB")
    except s3_client.exceptions.NoSuchKey:
        raise FileNotFoundError(
            f"Patch not found in S3: s3://{bucket}/{key}"
        )
    except Exception as exc:
        raise IOError(
            f"Failed to read patch from S3 (s3://{bucket}/{key}): {exc}"
        ) from exc


def _scan_all(table, **kwargs) -> list[dict]:
    """Paginate through a full DynamoDB table scan, returning all items.

    Args:
        table:    A boto3 DynamoDB Table resource.
        **kwargs: Additional arguments passed to ``table.scan()``.

    Returns:
        A flat list of all item dicts across all pages.
    """
    items: list[dict] = []
    resp = table.scan(**kwargs)
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **kwargs)
        items.extend(resp.get("Items", []))
    return items


def _query_patches_for_image(patch_table, image_id: str) -> list[dict]:
    """Query the Patches table for all patches belonging to an image.

    Uses the ``image_id-index`` GSI for efficient lookup. Falls back to a
    full table scan with a filter expression if the GSI doesn't exist
    (development environments only).

    Args:
        patch_table: A boto3 DynamoDB Table resource for patches.
        image_id:    The parent image UUID.

    Returns:
        A list of dicts with ``patch_id`` and ``patch_path`` keys.
    """
    try:
        resp = patch_table.query(
            IndexName="image_id-index",
            KeyConditionExpression=Key("image_id").eq(image_id),
            ProjectionExpression="patch_id, patch_path",
        )
        return resp.get("Items", [])
    except Exception:
        logger.warning(
            "GSI 'image_id-index' query failed for image %s; falling back to scan",
            image_id,
            exc_info=True,
        )
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
#   patch_path : S3 URI or bare key
#   label      : 1 = authentic, 0 = inauthentic
#   weight     : imitation_weight for inauthentic, 1.0 for authentic
#   sublabel   : "original" | "forgery" | "imitation" | "proxy" | None
#   image_id   : str  (used for painting-level aggregation in evaluate.py)

Sample = tuple[str, int, float, Optional[str], str]


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

class PatchDataset(Dataset):
    """PyTorch Dataset that streams 224x224 patches from S3 with DynamoDB labels.

    At construction time, scans DynamoDB to build an in-memory index of
    (patch_path, label, weight, sublabel, image_id) tuples. Each
    ``__getitem__`` call downloads the patch from S3 and applies transforms.

    Each ``__getitem__`` returns:
        ``(image_tensor, label, weight, sublabel, patch_path)``

    ``sublabel`` and ``patch_path`` are passed through as strings so
    evaluate.py can produce per-sublabel metric breakdowns and a full
    per-patch prediction log without extra DynamoDB lookups.

    Args:
        img_table_name:   DynamoDB Images table name.
        patch_table_name: DynamoDB Patches table name.
        processed_bucket: S3 bucket where patches are stored.
        region:           AWS region string.
        transform:        torchvision transform pipeline applied to each patch.
        imitation_weight: Per-sample weight for inauthentic patches (paper wim=10).
        split:            ``"train"``, ``"val"``, ``"test"``, or None (all records).
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
        """Initialize the dataset by scanning DynamoDB to build the patch index."""
        self.transform = transform or default_train_transforms()
        self.imitation_weight = imitation_weight
        self.processed_bucket = processed_bucket
        self.split = split

        self._s3 = boto3.client("s3", region_name=region)
        ddb = boto3.resource("dynamodb", region_name=region)
        img_table = ddb.Table(img_table_name)
        patch_table = ddb.Table(patch_table_name)

        self._samples: list[Sample] = []
        self._build_index(img_table, patch_table)

    def _build_index(self, img_table, patch_table) -> None:
        """Scan DynamoDB to build the in-memory sample index."""
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

            label = 1 if rec["label"] == "authentic" else 0
            weight = 1.0 if label == 1 else self.imitation_weight
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
        """Return the total number of patch samples in the dataset."""
        return len(self._samples)

    def __getitem__(self, idx: int):
        """Return the (image_tensor, label, weight, sublabel, patch_path) for one sample.

        Downloads the patch image from S3 on each call (no local caching).
        """
        patch_path, label, weight, sublabel, image_id = self._samples[idx]
        img = _stream_patch_from_s3(self._s3, patch_path, fallback_bucket=self.processed_bucket)
        if self.transform:
            img = self.transform(img)
        return img, label, weight, sublabel or "", patch_path

    @property
    def authentic_count(self) -> int:
        """Return the number of authentic (label=1) samples."""
        return sum(1 for s in self._samples if s[1] == 1)

    @property
    def contrast_count(self) -> int:
        """Return the number of inauthentic (label=0) samples."""
        return sum(1 for s in self._samples if s[1] == 0)

    @property
    def sublabel_counts(self) -> dict[str, int]:
        """Return a dict mapping each sublabel to its sample count.

        >>> ds.sublabel_counts  # doctest: +SKIP
        {'original': 150, 'forgery': 42, 'imitation': 18}
        """
        counts: dict[str, int] = {}
        for s in self._samples:
            sl = s[3] or "unlabelled"
            counts[sl] = counts.get(sl, 0) + 1
        return counts
