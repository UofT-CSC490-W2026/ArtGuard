#!/usr/bin/env bash
set -euo pipefail

# Run from repo root:
#   ./scripts/update-data-entry.sh
#
# Optional overrides:
#   DATA_DIR=./data METADATA_CSV=./data/metadata.csv ./scripts/update-data-entry.sh

ENVIRONMENT="dev"
AWS_REGION="${AWS_REGION:-ca-central-1}"

# These names match your Terraform naming convention:
PROJECT_NAME="${PROJECT_NAME:-artguard}"

export AWS_REGION="$AWS_REGION"
export S3_IMAGES_RAW_BUCKET="${PROJECT_NAME}-images-raw-${ENVIRONMENT}"
export DDB_IMAGES_TABLE="${PROJECT_NAME}-image-records-${ENVIRONMENT}"
export S3_RAW_PREFIX="${S3_RAW_PREFIX:-training/unprocessed}"

DATA_DIR="${DATA_DIR:-./data}"
METADATA_CSV="${METADATA_CSV:-./data/metadata.csv}"

chmod +x ./scripts/update-data.sh
./scripts/update-data.sh --data-dir "$DATA_DIR" --metadata "$METADATA_CSV"
