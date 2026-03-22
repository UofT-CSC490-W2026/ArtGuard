#!/bin/bash
set -e

# Bootstrap Terraform Infrastructure (First-Time Setup)
# Usage: ./bootstrap.sh [environment]
# Example: ./bootstrap.sh dev

source "$(dirname "$0")/_colors.sh"

ENVIRONMENT=${1:-dev}
AWS_REGION=${AWS_REGION:-ca-central-1}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

header "Terraform Bootstrap - ONE TIME SETUP"
echo -e "  Environment: ${CYAN}$ENVIRONMENT${NC}"
echo -e "  Region:      ${CYAN}$AWS_REGION${NC}"
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
  error "Aborted"
  exit 1
fi

cd "$ROOT_DIR/infra/terraform"

# Check if backend already exists
BUCKET_NAME="artguard-terraform-state"
STATE_KEY="$ENVIRONMENT/terraform.tfstate"

echo ""
step "Checking existing infrastructure..."

if command -v python3 &> /dev/null; then
  python3 -c "
import boto3
import sys
s3 = boto3.client('s3', region_name='$AWS_REGION')
try:
    s3.head_bucket(Bucket='$BUCKET_NAME')
    print('  S3 bucket already exists: $BUCKET_NAME')
except:
    print('  S3 bucket does not exist yet')
try:
    s3.head_object(Bucket='$BUCKET_NAME', Key='$STATE_KEY')
    print('  State file already exists: $STATE_KEY')
    print('  This environment may already be bootstrapped')
    sys.exit(1)
except:
    print('  State file does not exist yet')
" 2>/dev/null || {
    echo ""
    read -p "Continue anyway? (yes/no): " CONTINUE
    if [ "$CONTINUE" != "yes" ]; then
      echo "Aborted"
      exit 1
    fi
  }
else
  echo "  Python3 not available, skipping backend checks"
fi

# Validate Terraform configuration
echo ""
step "Validating Terraform configuration..."
terraform validate

# Plan
echo ""
step "Creating Terraform plan..."

if [ -f "$ENVIRONMENT.tfvars" ]; then
  TFVARS_FILE="$ENVIRONMENT.tfvars"
elif [ -f "../$ENVIRONMENT.tfvars" ]; then
  TFVARS_FILE="../$ENVIRONMENT.tfvars"
elif [ -f "$ROOT_DIR/$ENVIRONMENT.tfvars" ]; then
  TFVARS_FILE="$ROOT_DIR/$ENVIRONMENT.tfvars"
else
  echo "Error: $ENVIRONMENT.tfvars not found"
  echo "   Checked: $(pwd)/$ENVIRONMENT.tfvars"
  echo "   Checked: $(pwd)/../$ENVIRONMENT.tfvars"
  echo "   Checked: $ROOT_DIR/$ENVIRONMENT.tfvars"
  exit 1
fi

echo "Using variables file: $TFVARS_FILE"
terraform plan -var-file=$TFVARS_FILE -out=tfplan

echo ""
warn "IMPORTANT: Review the plan above before proceeding"
echo ""
read -p "Apply this plan? (yes/no): " APPLY

if [ "$APPLY" != "yes" ]; then
  error "Aborted"
  exit 1
fi

# Pre-apply: import any AWS resources that already exist (e.g. from a failed destroy)
echo ""
echo "Checking for existing resources that need importing..."

# DynamoDB tables
for tbl_suffix in users inference-records image-records patch-records run-records config-records; do
  tbl_name="artguard-${tbl_suffix}-${ENVIRONMENT}"
  tf_resource="aws_dynamodb_table.${tbl_suffix//-/_}"
  if aws dynamodb describe-table --table-name "$tbl_name" --region "$AWS_REGION" >/dev/null 2>&1; then
    terraform import -var-file="$TFVARS_FILE" "$tf_resource" "$tbl_name" 2>/dev/null \
      && echo "  Imported existing table: $tbl_name" \
      || echo "  Already in state: $tbl_name"
  fi
done

# S3 buckets
for bucket_suffix in images-raw knowledge-base frontend images-processed; do
  bucket_name="artguard-${bucket_suffix}-${ENVIRONMENT}"
  tf_resource="aws_s3_bucket.${bucket_suffix//-/_}"
  if aws s3api head-bucket --bucket "$bucket_name" --region "$AWS_REGION" 2>/dev/null; then
    terraform import -var-file="$TFVARS_FILE" "$tf_resource" "$bucket_name" 2>/dev/null \
      && echo "  Imported existing bucket: $bucket_name" \
      || echo "  Already in state: $bucket_name"
  fi
done

# Secrets (may be pending deletion or already exist)
echo ""
echo "Checking for existing secrets (pending deletion or active)..."
for secret_suffix in "modal-api-key" "jwt-secret"; do
  secret_name="artguard/${secret_suffix}-${ENVIRONMENT}"
  # Restore if pending deletion
  aws secretsmanager restore-secret \
    --secret-id "$secret_name" \
    --region "$AWS_REGION" 2>/dev/null \
    && echo "  Restored pending-deletion secret: $secret_name" || true
  # Import into terraform state if it exists in AWS but not in state
  secret_arn=$(aws secretsmanager describe-secret \
    --secret-id "$secret_name" \
    --region "$AWS_REGION" \
    --query 'ARN' --output text 2>/dev/null) || true
  if [[ -n "$secret_arn" && "$secret_arn" != "None" ]]; then
    tf_resource="aws_secretsmanager_secret.${secret_suffix//-/_}"
    terraform import "$tf_resource" "$secret_arn" 2>/dev/null \
      && echo "  Imported existing secret: $secret_name" \
      || echo "  Secret already in state: $secret_name"
  fi
done

# Re-plan after potential imports
echo ""
echo "Re-planning after secret imports..."
terraform plan -var-file=$TFVARS_FILE -out=tfplan

# Apply
echo ""
step "Applying Terraform configuration..."
terraform apply -auto-approve tfplan

echo ""
header "Bootstrap Complete!"
echo ""
info "Key Outputs:"
echo ""
echo -e "  ${BOLD}Frontend:${NC}"
terraform output cloudfront_distribution_url || echo -e "  ${DIM}Not available${NC}"
echo ""
echo -e "  ${BOLD}Backend API:${NC}"
terraform output backend_url || echo -e "  ${DIM}Not available${NC}"
echo ""
success "Your $ENVIRONMENT environment is ready!"
