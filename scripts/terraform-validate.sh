#!/bin/bash
set -e

# Validate Terraform Configuration (for PRs and manual checks)
# Usage: ./terraform-validate.sh [environment]
# Example: ./terraform-validate.sh dev

ENVIRONMENT=${1:-dev}
AWS_REGION=${AWS_REGION:-ca-central-1}
TERRAFORM_DIR="infra/terraform"

cd $TERRAFORM_DIR

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Terraform Validation & Plan"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Environment: $ENVIRONMENT"
echo "Backend Config: backend-$ENVIRONMENT.hcl"
echo "Variables File: $ENVIRONMENT.tfvars"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Format check
echo "Checking Terraform formatting..."
if terraform fmt -check -recursive; then
  echo "✅ Formatting is correct"
else
  echo "⚠️  Formatting issues found. Run: terraform fmt -recursive"
fi

echo ""

# TFLint (optional, if installed)
if command -v tflint &> /dev/null; then
  echo "Running TFLint..."
  tflint -f compact || echo "⚠️  TFLint warnings found"
  echo ""
else
  echo "TFLint not installed, skipping linting"
  echo "   Install: brew install tflint (Mac) or https://github.com/terraform-linters/tflint"
  echo ""
fi

# Initialize
echo "Initializing Terraform..."
terraform init -backend-config=backend-$ENVIRONMENT.hcl > /dev/null

# Validate
echo "✅ Validating Terraform configuration..."
terraform validate

# Plan
echo ""
echo "Creating Terraform plan..."
terraform plan -var-file=$ENVIRONMENT.tfvars -out=tfplan

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Validation Complete"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Plan saved to: tfplan"
echo ""
echo "To apply these changes, run:"
echo "  ./scripts/terraform-deploy.sh $ENVIRONMENT apply"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
