#!/bin/bash
set -e

# Setup AWS Secrets Manager Secrets
# Usage: ./setup-secrets.sh [environment]
# Example: ./setup-secrets.sh dev

source "$(dirname "$0")/_colors.sh"

export AWS_PAGER=""

ENVIRONMENT=${1:-dev}
AWS_REGION=${AWS_REGION:-ca-central-1}
SECRET_NAME="artguard/modal-api-key-$ENVIRONMENT"

header "Setting up AWS Secrets Manager"
echo -e "  Environment: ${CYAN}$ENVIRONMENT${NC}"
echo -e "  Region:      ${CYAN}$AWS_REGION${NC}"
echo -e "  Secret Name: ${CYAN}$SECRET_NAME${NC}"
echo ""

# Check if secret already has valid Modal credentials — skip if so
EXISTING=$(aws secretsmanager get-secret-value \
  --secret-id "$SECRET_NAME" \
  --region "$AWS_REGION" \
  --query SecretString --output text 2>/dev/null || echo "")

if [ -n "$EXISTING" ] && [ "$EXISTING" != "PLACEHOLDER" ] && [ "$EXISTING" != "REPLACE_WITH_LONG_RANDOM_STRING" ]; then
  success "Secret already configured. Skipping."
  exit 0
fi

# Accept MODAL_API_KEY from environment or prompt for both parts
if [ -n "${MODAL_API_KEY:-}" ] && [ "${MODAL_API_KEY}" != "PLACEHOLDER" ]; then
  info "Using MODAL_API_KEY from environment."
  SECRET_VALUE="$MODAL_API_KEY"
else
  read -sp "Enter Modal Token ID (ak-...): " TOKEN_ID
  echo ""
  read -sp "Enter Modal Token Secret: " TOKEN_SECRET
  echo ""

  if [ -z "$TOKEN_ID" ] || [ -z "$TOKEN_SECRET" ]; then
    error "Both Token ID and Token Secret are required."
    exit 1
  fi

  SECRET_VALUE="{\"token_id\":\"$TOKEN_ID\",\"token_secret\":\"$TOKEN_SECRET\"}"
fi

echo ""
step "Uploading secret to AWS Secrets Manager..."

aws secretsmanager put-secret-value \
  --secret-id "$SECRET_NAME" \
  --secret-string "$SECRET_VALUE" \
  --region "$AWS_REGION"

echo ""
header "Secret Updated Successfully"
success "Secret ARN:"
aws secretsmanager describe-secret \
  --secret-id $SECRET_NAME \
  --region $AWS_REGION \
  --query 'ARN' \
  --output text
echo ""
info "ECS tasks will automatically retrieve this secret on startup."
