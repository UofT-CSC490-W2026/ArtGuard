#!/bin/bash
set -e

# Disaster Recovery: Restore Modal API Key to AWS Secrets Manager
# Usage:
#   Local CLI:     MODAL_API_KEY=xxx ./secret_recovery.sh [environment]
#   GitHub Actions: (MODAL_API_KEY is set from GitHub Secrets)

ENVIRONMENT=${1:-dev}
AWS_REGION=${AWS_REGION:-ca-central-1}
SECRET_NAME="artguard/modal-api-key-$ENVIRONMENT"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Secret Recovery - Modal API Key"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Environment: $ENVIRONMENT"
echo "Region: $AWS_REGION"
echo "Secret: $SECRET_NAME"
echo ""

# Check if Modal API key is provided
if [ -z "$MODAL_API_KEY" ]; then
  echo "❌ Error: MODAL_API_KEY environment variable not set"
  echo ""
  echo "Usage:"
  echo "  Local CLI:"
  echo "    export MODAL_API_KEY='your-key-here'"
  echo "    ./secret_recovery.sh dev"
  echo ""
  echo "  Or one-liner:"
  echo "    MODAL_API_KEY='your-key-here' ./secret_recovery.sh dev"
  echo ""
  echo "  GitHub Actions:"
  echo "    MODAL_API_KEY is automatically set from GitHub Secrets"
  exit 1
fi

# Validate the key is not empty
if [ ${#MODAL_API_KEY} -lt 10 ]; then
  echo "❌ Error: MODAL_API_KEY appears to be invalid (too short)"
  exit 1
fi

echo "✅ Modal API key found (${#MODAL_API_KEY} characters)"
echo ""

# Upload to AWS Secrets Manager
echo "Uploading secret to AWS Secrets Manager..."

aws secretsmanager put-secret-value \
  --secret-id "$SECRET_NAME" \
  --secret-string "$MODAL_API_KEY" \
  --region "$AWS_REGION" \
  --no-cli-pager

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Recovery Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Secret ARN:"
aws secretsmanager describe-secret \
  --secret-id "$SECRET_NAME" \
  --region "$AWS_REGION" \
  --query 'ARN' \
  --output text

echo ""
echo "ECS tasks can now authenticate with Modal API"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
