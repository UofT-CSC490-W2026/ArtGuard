#!/bin/bash
set -e

# Setup AWS Secrets Manager Secrets
# Usage: ./setup-secrets.sh [environment]
# Example: ./setup-secrets.sh dev

ENVIRONMENT=${1:-dev}
AWS_REGION=${AWS_REGION:-ca-central-1}
SECRET_NAME="artguard/modal-api-key-$ENVIRONMENT"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Setting up AWS Secrets Manager"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Environment: $ENVIRONMENT"
echo "Region: $AWS_REGION"
echo "Secret Name: $SECRET_NAME"
echo ""

# Prompt for Modal API key
read -sp "Enter Modal API Key: " MODAL_API_KEY
echo ""

if [ -z "$MODAL_API_KEY" ]; then
  echo "❌ Modal API Key cannot be empty"
  exit 1
fi

echo ""
echo "📤 Uploading secret to AWS Secrets Manager..."

aws secretsmanager put-secret-value \
  --secret-id $SECRET_NAME \
  --secret-string "$MODAL_API_KEY" \
  --region $AWS_REGION \
  --no-cli-pager

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Secret Updated Successfully"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Secret ARN:"
aws secretsmanager describe-secret \
  --secret-id $SECRET_NAME \
  --region $AWS_REGION \
  --query 'ARN' \
  --output text
echo ""
echo "ECS tasks will automatically retrieve this secret on startup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
