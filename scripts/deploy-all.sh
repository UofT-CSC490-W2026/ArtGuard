#!/usr/bin/env bash
set -euo pipefail

# Deploy All ArtGuard Resources from Scratch
# Usage: ./scripts/deploy-all.sh [environment]
# Example: ./scripts/deploy-all.sh dev
#
# Prerequisites:
#   - AWS CLI v2 configured (aws configure)
#   - Terraform >= 1.10.0
#   - Docker Desktop running
#   - Python 3.11+
#   - awscurl (pip install awscurl)
#   - jq (brew install jq)
#   - Modal API key ready
#   - Pipeline output files in src/apps/data_pipeline/output/

source "$(dirname "$0")/_colors.sh"

ENVIRONMENT=${1:-dev}
AWS_REGION=${AWS_REGION:-ca-central-1}

header "ArtGuard Full Deployment"
echo -e "  Environment: ${CYAN}$ENVIRONMENT${NC}"
echo -e "  Region:      ${CYAN}$AWS_REGION${NC}"
echo ""

# ─── Step 1: Bootstrap Infrastructure (~15-20 min) ───
step "Step 1/7: Bootstrap Infrastructure"
echo -e "  ${DIM}Creates all AWS resources (VPC, ECS, S3, DynamoDB, OpenSearch, Bedrock KB, etc.)${NC}"
echo ""
./scripts/bootstrap.sh "$ENVIRONMENT"
echo ""

# ─── Step 2: Store Secrets ───
step "Step 2/7: Store Secrets"
info "You will be prompted for your Modal API key."
echo ""
./scripts/setup-secrets.sh "$ENVIRONMENT"
echo ""

# ─── Step 3: Build Docker Image (~5-10 min) ───
step "Step 3/7: Build and Push Docker Image"
./scripts/build-and-push-docker.sh "$ENVIRONMENT"
echo ""

# ─── Step 4: Deploy to ECS (~2-3 min) ───
step "Step 4/7: Deploy to ECS"
./scripts/deploy-ecs.sh "$ENVIRONMENT"
echo ""

# Wait for ECS to stabilize
BACKEND_URL=$(terraform -chdir=infra/terraform output -json summary | jq -r '.backend_url')
info "Waiting for backend to become healthy..."
echo -e "  URL: ${CYAN}${BACKEND_URL}/health${NC}"
MAX_RETRIES=20
RETRY=0
while [[ $RETRY -lt $MAX_RETRIES ]]; do
  HEALTH=$(curl -s "${BACKEND_URL}/health" 2>/dev/null || echo "unavailable")
  if echo "$HEALTH" | grep -q '"ok"'; then
    success "Backend is healthy!"
    break
  fi
  RETRY=$((RETRY + 1))
  echo -e "  ${DIM}Attempt $RETRY/$MAX_RETRIES — not ready yet, retrying in 15s...${NC}"
  sleep 15
done

if [[ $RETRY -eq $MAX_RETRIES ]]; then
  error "Backend did not become healthy after $((MAX_RETRIES * 15)) seconds."
  echo -e "  Check logs: ${CYAN}aws logs tail /ecs/artguard-backend --region $AWS_REGION --since 5m${NC}"
  exit 1
fi
echo ""

# ─── Step 5: Upload RAG Data and Ingest (~10-20 min) ───
step "Step 5/7: Upload RAG Data"
info "Converting JSONL to TXT and uploading to S3..."
./scripts/upload-rag-data.sh
echo ""

info "Ingestion has been triggered. This takes ~10-20 minutes."
echo ""

# Get ingestion job info
KB_ID=$(terraform -chdir=infra/terraform output -raw knowledge_base_id)
DS_ID=$(aws bedrock-agent list-data-sources \
  --knowledge-base-id "$KB_ID" \
  --region "$AWS_REGION" \
  --query "dataSourceSummaries[0].dataSourceId" \
  --output text)
JOB_ID=$(aws bedrock-agent list-ingestion-jobs \
  --knowledge-base-id "$KB_ID" \
  --data-source-id "$DS_ID" \
  --region "$AWS_REGION" \
  --query "ingestionJobSummaries[0].ingestionJobId" \
  --output text)

info "Waiting for ingestion to complete (checking every 30s)..."
while true; do
  STATUS=$(aws bedrock-agent get-ingestion-job \
    --knowledge-base-id "$KB_ID" \
    --data-source-id "$DS_ID" \
    --ingestion-job-id "$JOB_ID" \
    --region "$AWS_REGION" \
    --query "ingestionJob.status" \
    --output text 2>/dev/null || echo "UNKNOWN")

  INDEXED=$(aws bedrock-agent get-ingestion-job \
    --knowledge-base-id "$KB_ID" \
    --data-source-id "$DS_ID" \
    --ingestion-job-id "$JOB_ID" \
    --region "$AWS_REGION" \
    --query "ingestionJob.statistics.numberOfNewDocumentsIndexed" \
    --output text 2>/dev/null || echo "0")

  echo -e "  Status: ${YELLOW}$STATUS${NC} | Documents indexed: ${CYAN}$INDEXED${NC}"

  if [[ "$STATUS" == "COMPLETE" || "$STATUS" == "FAILED" || "$STATUS" == "STOPPED" ]]; then
    break
  fi
  sleep 30
done

echo ""
if [[ "$STATUS" == "COMPLETE" ]]; then
  success "Ingestion complete!"
else
  warn "Ingestion finished with status: $STATUS"
  echo -e "  Check: ${CYAN}aws bedrock-agent get-ingestion-job --knowledge-base-id $KB_ID --data-source-id $DS_ID --ingestion-job-id $JOB_ID --region $AWS_REGION${NC}"
fi
echo ""

# ─── Step 6: Upload Training Data ───
step "Step 6/7: Upload Training Data"

# Check if local images are real files or LFS pointers
SAMPLE_IMG=$(find data/ -name "*.jpg" -o -name "*.png" 2>/dev/null | head -1)
if [[ -n "$SAMPLE_IMG" ]] && file "$SAMPLE_IMG" | grep -q "image"; then
  info "Uploading training images to S3 and writing metadata to DynamoDB..."
  S3_IMAGES_RAW_BUCKET=$(terraform -chdir=infra/terraform output -raw s3_images_raw_bucket)
  DDB_IMAGES_TABLE=$(terraform -chdir=infra/terraform output -raw dynamodb_image_records_table_name)
  AWS_REGION="$AWS_REGION" \
  S3_IMAGES_RAW_BUCKET="$S3_IMAGES_RAW_BUCKET" \
  DDB_IMAGES_TABLE="$DDB_IMAGES_TABLE" \
  ./scripts/update-data.sh --data-dir ./data --metadata ./data/metadata.csv
else
  warn "Skipping — local images are Git LFS pointers (not real files)."
  echo -e "  To upload training data later, run:"
  echo -e "    ${GREEN}git lfs pull${NC}"
  echo -e "    ${DIM}S3_IMAGES_RAW_BUCKET=artguard-images-raw-$ENVIRONMENT \\${NC}"
  echo -e "    ${DIM}DDB_IMAGES_TABLE=artguard-image-records-$ENVIRONMENT \\${NC}"
  echo -e "    ${DIM}AWS_REGION=$AWS_REGION \\${NC}"
  echo -e "    ${DIM}./scripts/update-data.sh --data-dir ./data --metadata ./data/metadata.csv${NC}"
fi
echo ""

# ─── Step 7: Verify ───
step "Step 7/7: Verification"
echo ""

# Check vector count
ENDPOINT=$(terraform -chdir=infra/terraform output -raw opensearch_collection_endpoint)
info "Vector count:"
awscurl --service aoss --region "$AWS_REGION" "${ENDPOINT}/bedrock-knowledge-base-index/_count" 2>/dev/null || warn "Could not check vector count"
echo ""

# Health check
info "Health check:"
curl -s "${BACKEND_URL}/health"
echo ""
echo ""

# RAG query test
info "RAG query test:"
curl -s -X POST "${BACKEND_URL}/rag-query" \
  -H "Content-Type: application/json" \
  -d '{"query": "Tell me about Vincent van Gogh painting style"}' || warn "RAG query failed — Anthropic model access may still be pending"
echo ""

echo ""
header "Deployment Complete!"
echo ""
success "Backend URL: $BACKEND_URL"
echo ""
echo -e "Useful commands:"
echo -e "  ${GREEN}curl ${BACKEND_URL}/health${NC}                    # Health check"
echo -e "  ${GREEN}./scripts/ecs-control.sh scale $ENVIRONMENT 0${NC}  # Pause to save costs"
echo -e "  ${GREEN}./scripts/ecs-control.sh scale $ENVIRONMENT 1${NC}  # Resume"
echo -e "  ${RED}./scripts/destroy-all.sh $ENVIRONMENT${NC}         # Tear down everything"
