#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/_colors.sh"

# Upload local RAG pipeline output to the Knowledge Base S3 bucket
# and trigger a Bedrock Knowledge Base ingestion job.
#
# Usage:
#   ./scripts/upload-rag-data.sh
#
# Prerequisites:
#   - AWS credentials configured
#   - Terraform deployed (reads outputs for bucket name and KB ID)
#   - Pipeline output exists in one or both of:
#       src/apps/data_pipeline/output/
#       preprocessing/output/

JSONL_DIR="src/apps/data_pipeline/output"
TXT_DIR="src/apps/data_pipeline/output/txt"
TERRAFORM_DIR="infra/terraform"
S3_PREFIX="documents"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Upload RAG Data to S3"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Get config from Terraform outputs
BUCKET=$(terraform -chdir="$TERRAFORM_DIR" output -raw knowledge_base_s3_bucket 2>/dev/null) || {
  echo "Error: Could not read knowledge_base_s3_bucket from Terraform outputs." >&2
  echo "Make sure you have deployed with: cd $TERRAFORM_DIR && terraform apply" >&2
  exit 1
}
KB_ID=$(terraform -chdir="$TERRAFORM_DIR" output -raw knowledge_base_id 2>/dev/null) || {
  echo "Warning: Could not read knowledge_base_id. Skipping ingestion trigger." >&2
  KB_ID=""
}
AWS_REGION=$(terraform -chdir="$TERRAFORM_DIR" output -raw aws_region 2>/dev/null || echo "ca-central-1")

echo "Bucket:    $BUCKET"
echo "KB ID:     ${KB_ID:-<not set>}"
echo "Region:    $AWS_REGION"
echo ""

# Convert JSONL to TXT for Bedrock (Bedrock doesn't support .jsonl natively)
# Skip if TXT files already exist (e.g. from a previous run or checked into git)
TXT_COUNT=$(find "$TXT_DIR" -name "*.txt" 2>/dev/null | wc -l | tr -d ' ')
if [[ "$TXT_COUNT" -gt 0 ]]; then
  echo "Found $TXT_COUNT existing TXT files in $TXT_DIR — skipping JSONL conversion."
else
  echo "Converting JSONL files to TXT..."
  python3 scripts/convert-jsonl-to-txt.py
fi
echo ""

# Clear old documents from S3 first
echo "Clearing old documents from s3://$BUCKET/$S3_PREFIX/..."
aws s3 rm "s3://$BUCKET/$S3_PREFIX/" --recursive --region "$AWS_REGION" 2>/dev/null || true

# Upload .txt files
UPLOADED=0
for file in "$TXT_DIR"/*.txt; do
  [[ -f "$file" ]] || continue
  fname=$(basename "$file")
  echo "Uploading $fname -> s3://$BUCKET/$S3_PREFIX/$fname"
  aws s3 cp "$file" "s3://$BUCKET/$S3_PREFIX/$fname" --region "$AWS_REGION"
  UPLOADED=$((UPLOADED + 1))
done

if [[ $UPLOADED -eq 0 ]]; then
  echo "Error: No .txt files found in $TXT_DIR." >&2
  exit 1
fi

echo ""
echo "Uploaded $UPLOADED file(s) to s3://$BUCKET/$S3_PREFIX/"

# Trigger Knowledge Base ingestion
if [[ -n "$KB_ID" ]]; then
  echo ""
  echo "Triggering Knowledge Base ingestion..."
  DS_ID=$(aws bedrock-agent list-data-sources \
    --knowledge-base-id "$KB_ID" \
    --region "$AWS_REGION" \
    --query "dataSourceSummaries[0].dataSourceId" \
    --output text)

  if [[ -n "$DS_ID" && "$DS_ID" != "None" ]]; then
    JOB_ID=$(aws bedrock-agent start-ingestion-job \
      --knowledge-base-id "$KB_ID" \
      --data-source-id "$DS_ID" \
      --region "$AWS_REGION" \
      --query "ingestionJob.ingestionJobId" \
      --output text)
    echo "Ingestion job started: $JOB_ID"
    echo ""
    echo "Monitor with:"
    echo "  aws bedrock-agent get-ingestion-job --knowledge-base-id $KB_ID --data-source-id $DS_ID --ingestion-job-id $JOB_ID --region $AWS_REGION"
  else
    echo "Warning: No data source found for KB $KB_ID. Skipping ingestion." >&2
  fi
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Done"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
