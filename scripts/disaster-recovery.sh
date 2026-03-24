#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/_colors.sh"

# ArtGuard Disaster Recovery Demo
# Usage: ./scripts/disaster-recovery.sh [environment]
#
# This single script runs the full disaster recovery demonstration:
#   Phase 1 — Disaster simulation: saves Modal API key, then destroys all
#             stateless infra while orphaning data resources in AWS
#   Phase 2 — Proof: confirms DynamoDB tables and S3 buckets survived
#   Phase 3 — Recovery: re-imports orphaned data, recreates all stateless
#             infra, deploys app, re-syncs RAG, verifies everything

ENVIRONMENT=${1:-prod}
AWS_REGION=${AWS_REGION:-ca-central-1}
PROJECT_NAME="artguard"

USERS_TABLE="${PROJECT_NAME}-users-${ENVIRONMENT}"
IMAGES_RAW_BUCKET="${PROJECT_NAME}-images-raw-${ENVIRONMENT}"
KB_BUCKET="${PROJECT_NAME}-knowledge-base-${ENVIRONMENT}"

header "ArtGuard Disaster Recovery Demo"
echo -e "  Environment: ${CYAN}$ENVIRONMENT${NC}"
echo -e "  Region:      ${CYAN}$AWS_REGION${NC}"
echo ""
echo -e "This will:"
echo -e "  ${DIM}1. Save your Modal API key from Secrets Manager${NC}"
echo -e "  ${DIM}2. Destroy all stateless infrastructure (ECS, ALB, VPC, CloudFront, etc.)${NC}"
echo -e "  ${DIM}3. Prove data survived (DynamoDB + S3 still exist)${NC}"
echo -e "  ${DIM}4. Recover everything automatically${NC}"
echo ""
read -rp "Type DEMO to begin: " CONFIRM
if [[ "$CONFIRM" != "DEMO" ]]; then
  error "Aborted."
  exit 1
fi
echo ""

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 1 — DISASTER SIMULATION
# ═══════════════════════════════════════════════════════════════════════════
header "PHASE 1: Disaster Simulation"
echo ""

# Save Modal API key BEFORE destroying (destroy-all deletes the secret).
# Priority: local env var → AWS Secrets Manager → manual prompt.
# GitHub Actions: set MODAL_API_KEY as a repo secret and expose it in the
# workflow with `env: MODAL_API_KEY: ${{ secrets.MODAL_API_KEY }}` — the
# env var check below will pick it up automatically, no prompt needed.
step "Resolving Modal API key..."
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
echo ""

# Destroy stateless infra, preserve data as orphans.
step "Destroying stateless infrastructure (data is being orphaned)..."
echo ""
./scripts/destroy-all.sh "$ENVIRONMENT" --preserve-data <<< "DESTROY"

echo ""

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 2 — PROOF: DATA SURVIVED
# ═══════════════════════════════════════════════════════════════════════════
header "PHASE 2: Proof — Data Survived"
echo ""
info "Verifying orphaned resources still exist in AWS..."
echo -e "  ${DIM}(These have no Terraform owner — they survived the infrastructure destruction)${NC}"
echo ""

PROOF_PASS=0
PROOF_FAIL=0

check_survived() {
  local label="$1"
  local cmd="$2"
  if eval "$cmd" &>/dev/null; then
    echo -e "  ${GREEN}SURVIVED${NC}  $label"
    PROOF_PASS=$((PROOF_PASS + 1))
  else
    echo -e "  ${RED}MISSING${NC}   $label"
    PROOF_FAIL=$((PROOF_FAIL + 1))
  fi
}

check_survived "DynamoDB: ${PROJECT_NAME}-users-${ENVIRONMENT}" \
  "aws dynamodb describe-table --table-name ${PROJECT_NAME}-users-${ENVIRONMENT} --region $AWS_REGION"
check_survived "DynamoDB: ${PROJECT_NAME}-inference-records-${ENVIRONMENT}" \
  "aws dynamodb describe-table --table-name ${PROJECT_NAME}-inference-records-${ENVIRONMENT} --region $AWS_REGION"
check_survived "DynamoDB: ${PROJECT_NAME}-image-records-${ENVIRONMENT}" \
  "aws dynamodb describe-table --table-name ${PROJECT_NAME}-image-records-${ENVIRONMENT} --region $AWS_REGION"
check_survived "DynamoDB: ${PROJECT_NAME}-patch-records-${ENVIRONMENT}" \
  "aws dynamodb describe-table --table-name ${PROJECT_NAME}-patch-records-${ENVIRONMENT} --region $AWS_REGION"
check_survived "DynamoDB: ${PROJECT_NAME}-run-records-${ENVIRONMENT}" \
  "aws dynamodb describe-table --table-name ${PROJECT_NAME}-run-records-${ENVIRONMENT} --region $AWS_REGION"
check_survived "DynamoDB: ${PROJECT_NAME}-config-records-${ENVIRONMENT}" \
  "aws dynamodb describe-table --table-name ${PROJECT_NAME}-config-records-${ENVIRONMENT} --region $AWS_REGION"
check_survived "S3: ${IMAGES_RAW_BUCKET}" \
  "aws s3api head-bucket --bucket ${IMAGES_RAW_BUCKET} --region $AWS_REGION"
check_survived "S3: ${KB_BUCKET}" \
  "aws s3api head-bucket --bucket ${KB_BUCKET} --region $AWS_REGION"

echo ""
success "$PROOF_PASS/8 data resources confirmed alive in AWS with no Terraform owner."

if [[ $PROOF_FAIL -gt 0 ]]; then
  warn "$PROOF_FAIL resource(s) not found — recovery may be partial."
fi
echo ""

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 3 — RECOVERY
# ═══════════════════════════════════════════════════════════════════════════
header "PHASE 3: Recovery"
echo ""

MODAL_API_KEY="$MODAL_API_KEY" ./scripts/recover-prod.sh "$ENVIRONMENT"
