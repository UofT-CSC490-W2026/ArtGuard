#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/_colors.sh"

# ArtGuard Disaster Recovery Script
# Usage: ./scripts/recover-prod.sh [environment]
#
# What this does:
#   1. Verifies AWS credentials
#   2. Detects which data resources survived in AWS (as orphans)
#   3. Re-imports survivors into Terraform state
#   4. Runs terraform apply to recreate all stateless infrastructure
#      (ECS, ALB, VPC, CloudFront, OpenSearch, Bedrock KB, etc.)
#   5. Restores the Modal API key secret
#   6. Builds + pushes a fresh Docker image to the new ECR repository
#   7. Deploys the backend to ECS
#   8. Waits for the backend to become healthy
#   9. Triggers Bedrock Knowledge Base ingestion from the surviving S3 documents
#  10. Runs post-recovery verification
#
# Prerequisites:
#   - AWS CLI v2 configured with admin credentials
#   - Terraform >= 1.10.0
#   - Docker Desktop running
#   - Python 3.11+, jq, awscurl
#   - MODAL_API_KEY environment variable set (or will prompt)

ENVIRONMENT=${1:-prod}
AWS_REGION=${AWS_REGION:-ca-central-1}
TERRAFORM_DIR="infra/terraform"
PROJECT_NAME="artguard"

# ─── Deterministic resource names (match Terraform naming) ───────────────────
USERS_TABLE="${PROJECT_NAME}-users-${ENVIRONMENT}"
INFERENCE_TABLE="${PROJECT_NAME}-inference-records-${ENVIRONMENT}"
IMAGE_TABLE="${PROJECT_NAME}-image-records-${ENVIRONMENT}"
PATCH_TABLE="${PROJECT_NAME}-patch-records-${ENVIRONMENT}"
RUN_TABLE="${PROJECT_NAME}-run-records-${ENVIRONMENT}"
CONFIG_TABLE="${PROJECT_NAME}-config-records-${ENVIRONMENT}"
IMAGES_RAW_BUCKET="${PROJECT_NAME}-images-raw-${ENVIRONMENT}"
KB_BUCKET="${PROJECT_NAME}-knowledge-base-${ENVIRONMENT}"

# ─── Helpers ─────────────────────────────────────────────────────────────────
check_table() {
  aws dynamodb describe-table --table-name "$1" --region "$AWS_REGION" \
    --query "Table.TableStatus" --output text 2>/dev/null || echo "NOT_FOUND"
}

check_bucket() {
  if aws s3api head-bucket --bucket "$1" --region "$AWS_REGION" 2>/dev/null; then
    echo "EXISTS"
  elif aws s3 ls "s3://$1" --region "$AWS_REGION" 2>/dev/null >/dev/null; then
    echo "EXISTS"
  else
    echo "NOT_FOUND"
  fi
}

in_tf_state() {
  terraform -chdir="$TERRAFORM_DIR" state show "$1" &>/dev/null \
    && echo "true" || echo "false"
}

# Import a resource only if it's not already tracked in Terraform state.
import_if_needed() {
  local addr="$1"
  local aws_id="$2"
  if [[ "$(in_tf_state "$addr")" == "false" ]]; then
    info "Importing $addr ..."
    if ! terraform -chdir="$TERRAFORM_DIR" import \
      -var-file="${ENVIRONMENT}.tfvars" "$addr" "$aws_id" 2>&1; then
      warn "Import failed for $addr — will retry on next apply"
    fi
  else
    echo -e "  ${DIM}Already in state — skipping: $addr${NC}"
  fi
}

# ─── Header ──────────────────────────────────────────────────────────────────
header "ArtGuard Disaster Recovery"
echo -e "  Environment: ${CYAN}$ENVIRONMENT${NC}"
echo -e "  Region:      ${CYAN}$AWS_REGION${NC}"
echo ""

# ─── Step 1: Verify AWS credentials ──────────────────────────────────────────
step "[1/10] Verifying AWS credentials..."
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) || {
  error "AWS credentials not configured or expired."
  echo -e "  Run: ${GREEN}aws sso login${NC}  (or: ${GREEN}aws configure${NC})"
  exit 1
}
success "Authenticated as account: $ACCOUNT_ID"
echo ""

# ─── Step 2: Discover surviving resources ────────────────────────────────────
step "[2/10] Scanning for surviving data resources in AWS..."
echo ""

# Parallel arrays (bash 3 compatible — macOS ships bash 3.2)
TABLE_ADDRS=(
  "aws_dynamodb_table.users"
  "aws_dynamodb_table.inference_records"
  "aws_dynamodb_table.image_records"
  "aws_dynamodb_table.patch_records"
  "aws_dynamodb_table.run_records"
  "aws_dynamodb_table.config_records"
)
TABLE_NAMES=(
  "$USERS_TABLE"
  "$INFERENCE_TABLE"
  "$IMAGE_TABLE"
  "$PATCH_TABLE"
  "$RUN_TABLE"
  "$CONFIG_TABLE"
)

BUCKET_ADDRS=("aws_s3_bucket.images_raw" "aws_s3_bucket.knowledge_base")
BUCKET_NAMES=("$IMAGES_RAW_BUCKET" "$KB_BUCKET")
BUCKET_SUFFIXES=("images_raw" "knowledge_base")

info "DynamoDB tables:"
TABLES_FOUND=0
for i in 0 1 2 3 4 5; do
  name="${TABLE_NAMES[$i]}"
  status=$(check_table "$name")
  if [[ "$status" != "NOT_FOUND" ]]; then
    echo -e "    ${GREEN}FOUND${NC}   $name ($status)"
    TABLES_FOUND=$((TABLES_FOUND + 1))
  else
    echo -e "    ${RED}MISSING${NC} $name"
  fi
done

echo ""
info "S3 data buckets:"
BUCKETS_FOUND=0
for i in 0 1; do
  name="${BUCKET_NAMES[$i]}"
  status=$(check_bucket "$name")
  if [[ "$status" == "EXISTS" ]]; then
    echo -e "    ${GREEN}FOUND${NC}   $name"
    BUCKETS_FOUND=$((BUCKETS_FOUND + 1))
  else
    echo -e "    ${RED}MISSING${NC} $name"
  fi
done

echo ""
success "Found $TABLES_FOUND/6 DynamoDB tables and $BUCKETS_FOUND/2 data S3 buckets."
echo ""

# ─── Step 3: Terraform init ──────────────────────────────────────────────────
step "[3/10] Initialising Terraform..."
terraform -chdir="$TERRAFORM_DIR" init -reconfigure \
  -backend-config="backend-${ENVIRONMENT}.hcl"
echo ""

# ─── Step 4: Import surviving data resources into Terraform state ─────────────
step "[4/10] Importing surviving resources into Terraform state..."
echo ""

# DynamoDB tables — always attempt import
for i in 0 1 2 3 4 5; do
  addr="${TABLE_ADDRS[$i]}"
  name="${TABLE_NAMES[$i]}"
  import_if_needed "$addr" "$name"
done

# S3 buckets — always attempt import (check_bucket can be unreliable)
for i in 0 1; do
  addr="${BUCKET_ADDRS[$i]}"
  name="${BUCKET_NAMES[$i]}"
  suffix="${BUCKET_SUFFIXES[$i]}"
  import_if_needed "$addr" "$name"
  import_if_needed "aws_s3_bucket_versioning.${suffix}"                          "$name"
  import_if_needed "aws_s3_bucket_server_side_encryption_configuration.${suffix}" "$name"
  import_if_needed "aws_s3_bucket_public_access_block.${suffix}"                 "$name"
  import_if_needed "aws_s3_bucket_metric.${suffix}"                              "${name}:EntireBucket"

  # Lifecycle and policy only exist on images_raw
  if [[ "$suffix" == "images_raw" ]]; then
    import_if_needed "aws_s3_bucket_lifecycle_configuration.images_raw" "$name"
    import_if_needed "aws_s3_bucket_policy.images_raw"                  "$name"
  fi
done

echo ""

# ─── Step 4b: Handle secrets that may be pending deletion or orphaned ─────────
echo ""
info "Checking for existing secrets (pending deletion or active)..."
for secret_suffix in "modal-api-key" "jwt-secret"; do
  secret_name="${PROJECT_NAME}/${secret_suffix}-${ENVIRONMENT}"
  aws secretsmanager restore-secret \
    --secret-id "$secret_name" \
    --region "$AWS_REGION" 2>/dev/null \
    && warn "Restored pending-deletion secret: $secret_name" || true
  secret_arn=$(aws secretsmanager describe-secret \
    --secret-id "$secret_name" \
    --region "$AWS_REGION" \
    --query 'ARN' --output text 2>/dev/null) || true
  if [[ -n "${secret_arn:-}" && "$secret_arn" != "None" ]]; then
    tf_resource="aws_secretsmanager_secret.${secret_suffix//-/_}"
    terraform -chdir="$TERRAFORM_DIR" import \
      -var-file="${ENVIRONMENT}.tfvars" "$tf_resource" "$secret_arn" 2>/dev/null \
      && success "Imported existing secret: $secret_name" \
      || echo -e "    ${DIM}Secret already in state: $secret_name${NC}"
  fi
done
echo ""

# ─── Step 5: Terraform apply (recreates all stateless infra) ─────────────────
step "[5/10] Running terraform apply to recreate stateless infrastructure..."
echo -e "  ${DIM}VPC, ALB, ECS cluster, ECR, CloudFront, OpenSearch, Bedrock KB, IAM, monitoring...${NC}"
echo ""

# Force OpenSearch index re-creation — the collection is new (recreated by destroy)
# but null_resource.opensearch_index may still be in state, so Terraform skips it.
terraform -chdir="$TERRAFORM_DIR" taint null_resource.opensearch_index 2>/dev/null || true

terraform -chdir="$TERRAFORM_DIR" apply \
  -var-file="${ENVIRONMENT}.tfvars" \
  -auto-approve
echo ""

# ─── Step 6: Restore secrets ─────────────────────────────────────────────────
step "[6/10] Restoring secrets..."
if [[ -n "${MODAL_API_KEY:-}" && "${MODAL_API_KEY}" != "PLACEHOLDER" ]]; then
  success "Using MODAL_API_KEY from environment."
else
  info "Checking AWS Secrets Manager..."
  MODAL_API_KEY=$(aws secretsmanager get-secret-value \
    --secret-id "${PROJECT_NAME}/modal-api-key-${ENVIRONMENT}" \
    --region "$AWS_REGION" \
    --query SecretString \
    --output text 2>/dev/null || echo "")
  if [[ -n "$MODAL_API_KEY" && "$MODAL_API_KEY" != "PLACEHOLDER" ]]; then
    success "Found key in Secrets Manager."
  else
    warn "Not found anywhere. Enter Modal credentials manually:"
    read -rsp "  Modal Token ID (ak-...): " TOKEN_ID
    echo ""
    read -rsp "  Modal Token Secret: " TOKEN_SECRET
    echo ""
    MODAL_API_KEY="{\"token_id\":\"$TOKEN_ID\",\"token_secret\":\"$TOKEN_SECRET\"}"
  fi
fi
MODAL_API_KEY="$MODAL_API_KEY" ./scripts/setup-secrets.sh "$ENVIRONMENT"
echo ""

# ─── Step 7: Build + push Docker image ───────────────────────────────────────
step "[7/10] Building and pushing Docker image to new ECR repository..."
./scripts/build-and-push-docker.sh "$ENVIRONMENT"
echo ""

# ─── Step 8: Deploy to ECS and wait for health ───────────────────────────────
step "[8/10] Deploying to ECS..."
./scripts/deploy-ecs.sh "$ENVIRONMENT"
echo ""

BACKEND_URL=$(terraform -chdir="$TERRAFORM_DIR" output -json summary | jq -r '.backend_url')
info "Backend URL: ${BOLD}$BACKEND_URL${NC}"
info "Waiting for /health to respond..."

MAX_RETRIES=20
RETRY=0
until [[ $RETRY -ge $MAX_RETRIES ]]; do
  HEALTH=$(curl -sf "${BACKEND_URL}/health" 2>/dev/null || echo "unavailable")
  if echo "$HEALTH" | grep -q '"ok"'; then
    success "Backend is healthy!"
    break
  fi
  RETRY=$((RETRY + 1))
  echo -e "  ${DIM}Attempt $RETRY/$MAX_RETRIES — not ready, retrying in 15s...${NC}"
  sleep 15
done

if [[ $RETRY -ge $MAX_RETRIES ]]; then
  error "Backend did not become healthy after $((MAX_RETRIES * 15))s."
  echo -e "  Check logs: ${CYAN}aws logs tail /ecs/artguard-backend --region $AWS_REGION --since 5m${NC}"
  exit 1
fi
echo ""

# ─── Step 9: Re-sync Bedrock Knowledge Base ───────────────────────────────────
# The knowledge-base S3 bucket survived — its documents are still there.
# The OpenSearch collection and Bedrock KB were recreated by terraform apply,
# so we just need to trigger a fresh ingestion job.
step "[9/10] Triggering Bedrock Knowledge Base ingestion from surviving S3 documents..."
KB_ID=$(terraform -chdir="$TERRAFORM_DIR" output -raw knowledge_base_id)
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
  success "Ingestion job started: $JOB_ID"
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
    echo -e "    Status: ${YELLOW}$STATUS${NC} | Documents indexed: ${CYAN}$INDEXED${NC}"
    [[ "$STATUS" == "COMPLETE" || "$STATUS" == "FAILED" || "$STATUS" == "STOPPED" ]] && break
    sleep 30
  done
  if [[ "$STATUS" != "COMPLETE" ]]; then
    warn "Ingestion ended with status $STATUS. RAG may be degraded."
  fi
else
  warn "No data source found for KB $KB_ID. Run ${CYAN}./scripts/upload-rag-data.sh${NC} manually."
fi
echo ""

# ─── Step 10: Post-recovery verification ─────────────────────────────────────
step "[10/10] Post-recovery verification..."
echo ""

PASS=0
FAIL=0

verify() {
  local label="$1"
  local cmd="$2"
  local expected="$3"
  result=$(eval "$cmd" 2>/dev/null || echo "ERROR")
  if echo "$result" | grep -q "$expected"; then
    echo -e "  ${GREEN}PASS${NC}  $label"
    PASS=$((PASS + 1))
  else
    echo -e "  ${RED}FAIL${NC}  $label (got: $result)"
    FAIL=$((FAIL + 1))
  fi
}

# DynamoDB tables
verify "DynamoDB users table" \
  "aws dynamodb describe-table --table-name $USERS_TABLE --region $AWS_REGION --query Table.TableStatus --output text" \
  "ACTIVE"
verify "DynamoDB inference_records table" \
  "aws dynamodb describe-table --table-name $INFERENCE_TABLE --region $AWS_REGION --query Table.TableStatus --output text" \
  "ACTIVE"
verify "DynamoDB image_records table" \
  "aws dynamodb describe-table --table-name $IMAGE_TABLE --region $AWS_REGION --query Table.TableStatus --output text" \
  "ACTIVE"
verify "DynamoDB patch_records table" \
  "aws dynamodb describe-table --table-name $PATCH_TABLE --region $AWS_REGION --query Table.TableStatus --output text" \
  "ACTIVE"
verify "DynamoDB run_records table" \
  "aws dynamodb describe-table --table-name $RUN_TABLE --region $AWS_REGION --query Table.TableStatus --output text" \
  "ACTIVE"
verify "DynamoDB config_records table" \
  "aws dynamodb describe-table --table-name $CONFIG_TABLE --region $AWS_REGION --query Table.TableStatus --output text" \
  "ACTIVE"

# S3 buckets
verify "S3 images-raw bucket accessible" \
  "aws s3api head-bucket --bucket $IMAGES_RAW_BUCKET --region $AWS_REGION && echo OK" \
  "OK"
verify "S3 knowledge-base bucket accessible" \
  "aws s3api head-bucket --bucket $KB_BUCKET --region $AWS_REGION && echo OK" \
  "OK"

# Backend health
verify "Backend /health endpoint" \
  "curl -sf ${BACKEND_URL}/health" \
  "ok"

# RAG query
verify "RAG /rag-query endpoint" \
  "curl -sf -X POST ${BACKEND_URL}/rag-query -H 'Content-Type: application/json' -d '{\"query\":\"Vincent van Gogh\"}'" \
  "answer"

echo ""
if [[ $FAIL -eq 0 ]]; then
  header "Recovery Complete — all $PASS checks passed"
else
  header "Recovery Complete — $PASS passed, $FAIL FAILED"
  warn "Review failures above before considering the system restored."
fi
FRONTEND_URL=$(terraform -chdir="$TERRAFORM_DIR" output -raw cloudfront_distribution_url 2>/dev/null || echo "N/A")
ALB_URL=$(terraform -chdir="$TERRAFORM_DIR" output -raw alb_dns_name 2>/dev/null || echo "N/A")
echo ""
echo -e "  Frontend URL: ${GREEN}$FRONTEND_URL${NC}"
echo -e "  Backend URL:  ${GREEN}$BACKEND_URL${NC}"
echo -e "  ALB URL:      ${GREEN}$ALB_URL${NC}"
echo ""
info "These URLs are NEW after recovery."
echo -e "  ${DIM}If you have a custom domain, it will route to the new ALB automatically.${NC}"
