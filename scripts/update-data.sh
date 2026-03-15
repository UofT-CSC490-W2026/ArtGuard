#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./scripts/update-data.sh --data-dir ./data --metadata ./data/metadata.csv
#
# Required env vars (match your app):
#   AWS_REGION
#   S3_IMAGES_RAW_BUCKET
#   DDB_IMAGES_TABLE
#
# Optional:
#   S3_RAW_PREFIX (default: training/unprocessed)
#   DRY_RUN=1 (do not upload or write to DDB)
#   FORCE_UPLOAD=1 (upload even if object exists)
#
# Example:
#   export AWS_REGION=ca-central-1
#   export S3_IMAGES_RAW_BUCKET=artguard-images-raw-dev
#   export DDB_IMAGES_TABLE=artguard-image-records-dev
#   ./scripts/update-data.sh --data-dir ./data --metadata ./data/metadata.csv

DATA_DIR="./data"
METADATA_CSV="./data/metadata.csv"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --data-dir)
      DATA_DIR="$2"
      shift 2
      ;;
    --metadata)
      METADATA_CSV="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

: "${AWS_REGION:?Must set AWS_REGION}"
: "${S3_IMAGES_RAW_BUCKET:?Must set S3_IMAGES_RAW_BUCKET}"
: "${DDB_IMAGES_TABLE:?Must set DDB_IMAGES_TABLE}"
S3_RAW_PREFIX="${S3_RAW_PREFIX:-training/unprocessed}"

if [[ ! -d "$DATA_DIR" ]]; then
  echo "DATA_DIR not found: $DATA_DIR" >&2
  exit 1
fi

if [[ ! -f "$METADATA_CSV" ]]; then
  echo "METADATA_CSV not found: $METADATA_CSV" >&2
  exit 1
fi

# Export for the embedded Python script
export DATA_DIR METADATA_CSV S3_RAW_PREFIX

echo "DATA_DIR:      $DATA_DIR"
echo "METADATA_CSV:  $METADATA_CSV"
echo "AWS_REGION:    $AWS_REGION"
echo "RAW_BUCKET:    $S3_IMAGES_RAW_BUCKET"
echo "RAW_PREFIX:    $S3_RAW_PREFIX"
echo "DDB_TABLE:     $DDB_IMAGES_TABLE"
echo "DRY_RUN:       ${DRY_RUN:-0}"
echo "FORCE_UPLOAD:  ${FORCE_UPLOAD:-0}"
echo

python3 - <<'PY'
import csv
import os
import sys
from typing import Dict, List, Optional, Tuple
import boto3
from botocore.exceptions import ClientError

DATA_DIR = os.path.abspath(os.environ.get("DATA_DIR", "./data"))
METADATA_CSV = os.path.abspath(os.environ.get("METADATA_CSV", "./data/metadata.csv"))
AWS_REGION = os.environ["AWS_REGION"]
RAW_BUCKET = os.environ["S3_IMAGES_RAW_BUCKET"]
DDB_TABLE = os.environ["DDB_IMAGES_TABLE"]
RAW_PREFIX = os.environ.get("S3_RAW_PREFIX", "training/unprocessed").strip().strip("/")
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"
FORCE_UPLOAD = os.environ.get("FORCE_UPLOAD", "0") == "1"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}


def build_filename_index(root_dir: str) -> Dict[str, List[str]]:
    """Map filename -> [full local paths...]"""
    idx: Dict[str, List[str]] = {}
    for base, _, files in os.walk(root_dir):
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext in IMAGE_EXTS:
                full = os.path.join(base, fn)
                idx.setdefault(fn, []).append(full)
    return idx


def s3_object_exists(s3, bucket: str, key: str) -> bool:
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def upload_file(s3, local_path: str, bucket: str, key: str) -> None:
    s3.upload_file(
        Filename=local_path,
        Bucket=bucket,
        Key=key,
        ExtraArgs={"ServerSideEncryption": "AES256"},
    )


def to_ddb_item(row: dict, s3_uri: str) -> dict:
    """
    Build a DynamoDB ImageRecord item from a CSV row.
    Uses the actual uploaded S3 URI (not the CSV's original path).
    """
    def nonempty(v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = str(v).strip()
        return v if v != "" else None

    item = {
        "image_id": row["image_id"],
        "created_at": int(row["created_at"]) if row.get("created_at") else 0,
        "image_name": row.get("image_name", ""),
        "image_path": s3_uri,
        "image_width": int(row["image_width"]) if row.get("image_width") else 0,
        "image_height": int(row["image_height"]) if row.get("image_height") else 0,
        "label": row.get("label", ""),
        "split": "unassigned",
    }

    for k in ["sublabel", "run_id", "fold_id", "attributed_creator", "actual_creator"]:
        v = nonempty(row.get(k))
        if v is None:
            continue
        if k == "fold_id":
            try:
                item[k] = int(v)
            except ValueError:
                continue
        else:
            item[k] = v

    return item


def main() -> int:
    print("Indexing local images (by filename)...", flush=True)
    idx = build_filename_index(DATA_DIR)
    print(f"Found {sum(len(v) for v in idx.values())} image files under {DATA_DIR}", flush=True)

    s3 = boto3.client("s3", region_name=AWS_REGION)
    ddb = boto3.resource("dynamodb", region_name=AWS_REGION)
    table = ddb.Table(DDB_TABLE)

    uploaded = 0
    skipped_upload_exists = 0
    missing_local = 0
    ambiguous_local = 0
    ddb_written = 0

    with open(METADATA_CSV, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Loaded {len(rows)} metadata rows", flush=True)

    if DRY_RUN:
        batch_ctx = None
    else:
        batch_ctx = table.batch_writer(overwrite_by_pkeys=["image_id"])

    try:
        for row in rows:
            image_id = row.get("image_id", "").strip()
            image_name = row.get("image_name", "").strip()

            if not image_id or not image_name:
                print("[WARN] Skipping row with missing image_id or image_name", flush=True)
                continue

            # Find local file by filename
            matches = idx.get(image_name, [])
            if not matches:
                print(f"[WARN] Local file not found for image_name={image_name}", flush=True)
                missing_local += 1
                continue
            if len(matches) > 1:
                print(f"[WARN] Multiple local files named {image_name}. Using first:\n  {matches[0]}\n  others={len(matches)-1}", flush=True)
                ambiguous_local += 1

            local_path = matches[0]

            # Always upload to training/unprocessed/{image_id}/{filename}
            key = f"{RAW_PREFIX}/{image_id}/{image_name}"
            s3_uri = f"s3://{RAW_BUCKET}/{key}"

            do_upload = FORCE_UPLOAD or (not s3_object_exists(s3, RAW_BUCKET, key))
            if DRY_RUN:
                print(f"[DRY_RUN] Would upload: {local_path} -> {s3_uri}", flush=True)
            else:
                if do_upload:
                    upload_file(s3, local_path, RAW_BUCKET, key)
                    uploaded += 1
                else:
                    skipped_upload_exists += 1

            # Write ImageRecord to DynamoDB with the actual S3 URI
            item = to_ddb_item(row, s3_uri)

            if DRY_RUN:
                print(f"[DRY_RUN] Would write DDB item: image_id={item['image_id']} label={item.get('label')}", flush=True)
            else:
                batch_ctx.put_item(Item=item)
                ddb_written += 1

    finally:
        if batch_ctx is not None:
            batch_ctx.__exit__(None, None, None)

    print("\nDone.")
    print(f"Uploaded to S3:            {uploaded}")
    print(f"Skipped (already exists):  {skipped_upload_exists}")
    print(f"Missing local files:       {missing_local}")
    print(f"Ambiguous filename matches:{ambiguous_local}")
    print(f"DDB records written:       {ddb_written}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
PY
