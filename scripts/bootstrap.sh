#!/bin/bash
set -e

# Bootstrap Terraform Infrastructure (First-Time Setup)
# Usage: ./bootstrap.sh [environment]
# Example: ./bootstrap.sh dev

ENVIRONMENT=${1:-dev}
AWS_REGION=${AWS_REGION:-ca-central-1}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Terraform Bootstrap - ONE TIME SETUP"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Environment: $ENVIRONMENT"
echo "Region: $AWS_REGION"
echo ""
echo "This will:"
echo "  1. Create S3 bucket for Terraform state"
echo "  2. Create DynamoDB table for state locking"
echo "  3. Initialize Terraform backend"
echo "  4. Create all infrastructure resources"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Confirm before proceeding
read -p "Type 'BOOTSTRAP' to confirm: " CONFIRM

if [ "$CONFIRM" != "BOOTSTRAP" ]; then
  echo "❌ Aborted"
  exit 1
fi

cd infra/terraform

# Check if backend already exists
BUCKET_NAME="artguard-terraform-state"
STATE_KEY="$ENVIRONMENT/terraform.tfstate"

echo ""
echo "🔍 Checking existing infrastructure..."

if aws s3 ls "s3://$BUCKET_NAME" 2>/dev/null; then
  echo "⚠️  S3 bucket already exists: $BUCKET_NAME"
else
  echo "✅ S3 bucket does not exist yet"
fi

if aws s3 ls "s3://$BUCKET_NAME/$STATE_KEY" 2>/dev/null; then
  echo "⚠️  State file already exists: $STATE_KEY"
  echo "⚠️  This environment may already be bootstrapped"
  echo ""
  read -p "Continue anyway? (yes/no): " CONTINUE
  if [ "$CONTINUE" != "yes" ]; then
    echo "❌ Aborted"
    exit 1
  fi
else
  echo "✅ State file does not exist yet"
fi

# Setup backend (S3 + DynamoDB)
echo ""
echo "Setting up backend..."
if [ -f "setup-backend.sh" ]; then
  chmod +x setup-backend.sh
  ./setup-backend.sh
else
  echo "⚠️  setup-backend.sh not found, skipping..."
fi

# Initialize Terraform
echo ""
echo "🔧 Initializing Terraform..."
terraform init -backend-config="key=$STATE_KEY" -backend-config="region=$AWS_REGION"

# Validate
echo ""
echo "✅ Validating Terraform configuration..."
terraform validate

# Plan
echo ""
echo "Creating Terraform plan..."
terraform plan -var-file=$ENVIRONMENT.tfvars -out=tfplan

echo ""
echo "⚠️  IMPORTANT: Review the plan above before proceeding"
echo ""
read -p "Apply this plan? (yes/no): " APPLY

if [ "$APPLY" != "yes" ]; then
  echo "❌ Aborted"
  exit 1
fi

# Apply
echo ""
echo "Applying Terraform configuration..."
terraform apply -auto-approve tfplan

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Bootstrap Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Key Outputs:"
echo ""
echo "Frontend:"
terraform output cloudfront_distribution_url || echo "  Not available"
echo ""
echo "Backend API:"
terraform output backend_url || echo "  Not available"
echo ""
echo "🎉 Your $ENVIRONMENT environment is ready!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
