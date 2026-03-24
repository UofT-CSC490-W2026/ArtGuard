#!/usr/bin/env bash
set -euo pipefail

# Upload local images to S3 and write metadata to DynamoDB.
#
# Usage:
#   ./scripts/update-data.sh --data-dir ./data --metadata ./data/metadata.csv
#
# Required env vars:
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

source "$(dirname "$0")/_colors.sh"

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

export DATA_DIR METADATA_CSV S3_RAW_PREFIX

header "Upload Images to S3 + DynamoDB"
echo -e "  DATA_DIR:     ${CYAN}$DATA_DIR${NC}"
echo -e "  METADATA_CSV: ${CYAN}$METADATA_CSV${NC}"
echo -e "  AWS_REGION:   ${CYAN}$AWS_REGION${NC}"
echo -e "  RAW_BUCKET:   ${CYAN}$S3_IMAGES_RAW_BUCKET${NC}"
echo -e "  RAW_PREFIX:   ${CYAN}$S3_RAW_PREFIX${NC}"
echo -e "  DDB_TABLE:    ${CYAN}$DDB_IMAGES_TABLE${NC}"
echo -e "  DRY_RUN:      ${YELLOW}${DRY_RUN:-0}${NC}"
echo -e "  FORCE_UPLOAD: ${YELLOW}${FORCE_UPLOAD:-0}${NC}"
echo

python3 - <<'PY'
import csv
import os
import re
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


def normalize_relpath(p: str) -> str:
    """Normalize path separators and strip leading ./ for consistent matching."""
    return p.replace("\\", "/").strip().lstrip("./")


def build_indexes(root_dir: str) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    """Build lookup indexes for local image files.

    Returns:
        relpath_index:  relative path from DATA_DIR -> absolute path
        filename_index: basename -> [absolute paths]
    """
    relpath_index: Dict[str, str] = {}
    filename_index: Dict[str, List[str]] = {}

    for base, _, files in os.walk(root_dir):
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in IMAGE_EXTS:
                continue

            full = os.path.join(base, fn)
            rel = normalize_relpath(os.path.relpath(full, root_dir))

            relpath_index[rel] = full
            filename_index.setdefault(fn, []).append(full)

    return relpath_index, filename_index


def s3_object_exists(s3, bucket: str, key: str) -> bool:
    """Check if an S3 object exists without downloading it."""
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def upload_file(s3, local_path: str, bucket: str, key: str) -> None:
    """Upload a local file to S3 with server-side encryption."""
    s3.upload_file(
        Filename=local_path,
        Bucket=bucket,
        Key=key,
        ExtraArgs={"ServerSideEncryption": "AES256"},
    )

def infer_split_from_path(path: str) -> Optional[str]:
    p = normalize_relpath(path).lower()
    if re.search(r"(^|[/_.-])(train)([/_.-]|$)", p):
        return "train"
    if re.search(r"(^|[/_.-])(val|valid|validation)([/_.-]|$)", p):
        return "val"
    if re.search(r"(^|[/_.-])(test)([/_.-]|$)", p):
        return "test"
    return None


def to_ddb_item(row: dict, s3_uri: str, local_relpath: Optional[str] = None) -> dict:
    """
    Build a DynamoDB ImageRecord item from a CSV row.
    Uses the actual uploaded S3 URI (not the CSV's original path).
    Leaves CSV metadata intact.
    """
    def nonempty(v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = str(v).strip()
        return v if v != "" else None

    # Prefer path relative to DATA_DIR (actual on-disk location), then CSV image_name.
    split_from_path = infer_split_from_path(local_relpath or "")
    if split_from_path is None:
        split_from_path = infer_split_from_path(row.get("image_name") or "")

    item = {
        "image_id": row["image_id"],
        "created_at": int(row["created_at"]) if row.get("created_at") else 0,
        "image_name": row.get("image_name", ""),
        "image_path": s3_uri,
        "image_width": int(row["image_width"]) if row.get("image_width") else 0,
        "image_height": int(row["image_height"]) if row.get("image_height") else 0,
        "label": row.get("label", ""),
        "split": split_from_path or (row.get("split", "unassigned") or "unassigned"),
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


def find_local_file(
    row: dict,
    relpath_index: Dict[str, str],
    filename_index: Dict[str, List[str]],
) -> Tuple[Optional[str], Optional[str]]:
    """Resolve a local file for a metadata row.

    Strategy:
      1) Exact relative-path match under DATA_DIR.
      2) Basename fallback across the full data tree.

    Returns:
      (local_path, warning_message)
    """
    image_name = (row.get("image_name") or "").strip()
    if not image_name:
        return None, "missing image_name"

    image_name_norm = normalize_relpath(image_name)

    if image_name_norm in relpath_index:
        return relpath_index[image_name_norm], None

    basename = os.path.basename(image_name_norm)
    matches = filename_index.get(basename, [])

    if not matches:
        return None, f"Local file not found for image_name={image_name}"

    if len(matches) > 1:
        chosen = matches[0]
        return chosen, (
            f"Multiple local files named {basename}. Using first:\n"
            f"  {chosen}\n"
            f"  others={len(matches)-1}"
        )

    return matches[0], None


def main() -> int:
    print("Indexing local images...", flush=True)
    relpath_index, filename_index = build_indexes(DATA_DIR)
    print(f"Found {len(relpath_index)} image files under {DATA_DIR}", flush=True)

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
        batch_ctx.__enter__()

    try:
        for row in rows:
            image_id = row.get("image_id", "").strip()
            image_name = row.get("image_name", "").strip()

            if not image_id or not image_name:
                print("[WARN] Skipping row with missing image_id or image_name", flush=True)
                continue

            local_path, warn = find_local_file(row, relpath_index, filename_index)
            if not local_path:
                print(f"[WARN] {warn}", flush=True)
                missing_local += 1
                continue

            if warn:
                print(f"[WARN] {warn}", flush=True)
                if "Multiple local files named" in warn:
                    ambiguous_local += 1

            key = f"{RAW_PREFIX}/{image_id}/{os.path.basename(local_path)}"
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

            local_relpath = normalize_relpath(os.path.relpath(local_path, DATA_DIR))
            item = to_ddb_item(row, s3_uri, local_relpath=local_relpath)

            if DRY_RUN:
                print(
                    f"[DRY_RUN] Would write DDB item: image_id={item['image_id']} "
                    f"label={item.get('label')} split={item.get('split')}",
                    flush=True,
                )
            else:
                batch_ctx.put_item(Item=item)
                ddb_written += 1

    finally:
        if batch_ctx is not None:
            batch_ctx.__exit__(None, None, None)

    print("\nDone.")
    print(f"Uploaded to S3:             {uploaded}")
    print(f"Skipped (already exists):   {skipped_upload_exists}")
    print(f"Missing local files:        {missing_local}")
    print(f"Ambiguous filename matches: {ambiguous_local}")
    print(f"DDB records written:        {ddb_written}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
PY
