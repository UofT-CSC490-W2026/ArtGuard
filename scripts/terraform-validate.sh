#!/bin/bash
set -e

# Validate Terraform Configuration (for PRs and manual checks)
# Usage: ./terraform-validate.sh [environment]
# Example: ./terraform-validate.sh dev

source "$(dirname "$0")/_colors.sh"

ENVIRONMENT=${1:-dev}
AWS_REGION=${AWS_REGION:-ca-central-1}
TERRAFORM_DIR="infra/terraform"

cd $TERRAFORM_DIR

header "Terraform Validation & Plan"
echo -e "  Environment:    ${CYAN}$ENVIRONMENT${NC}"
echo -e "  Backend Config: ${CYAN}backend-$ENVIRONMENT.hcl${NC}"
echo -e "  Variables File: ${CYAN}$ENVIRONMENT.tfvars${NC}"
echo ""

# Format check
step "Checking Terraform formatting..."
if terraform fmt -check -recursive; then
  success "Formatting is correct"
else
  warn "Formatting issues found. Run: terraform fmt -recursive"
fi

echo ""

# TFLint (optional, if installed)
if command -v tflint &> /dev/null; then
  step "Running TFLint..."
  tflint -f compact || warn "TFLint warnings found"
  echo ""
else
  echo -e "${DIM}TFLint not installed, skipping linting${NC}"
  echo -e "  ${DIM}Install: brew install tflint (Mac) or https://github.com/terraform-linters/tflint${NC}"
  echo ""
fi

# Initialize
step "Initializing Terraform..."
terraform init -backend-config=backend-$ENVIRONMENT.hcl > /dev/null

# Validate
step "Validating Terraform configuration..."
terraform validate
success "Terraform config is valid"

# Plan
echo ""
step "Creating Terraform plan..."
terraform plan -var-file=$ENVIRONMENT.tfvars -out=tfplan

echo ""
header "Validation Complete"
success "Plan saved to: tfplan"
echo ""
echo -e "To apply these changes, run:"
echo -e "  ${GREEN}./scripts/terraform-deploy.sh $ENVIRONMENT apply${NC}"
