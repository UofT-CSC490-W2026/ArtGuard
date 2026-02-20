#!/bin/bash
set -e

# Bootstrap Terraform Infrastructure (First-Time Setup)
# Usage: ./bootstrap.sh [environment]
# Example: ./bootstrap.sh dev

# Ensure AWS CLI is in PATH (for pip-installed versions)
# Add user local bin to PATH if it exists
# if [ -d "$HOME/.local/bin" ]; then
#   export PATH="$HOME/.local/bin:$PATH"
# fi
# # Also check for AWS CLI in common locations
# if ! command -v aws &> /dev/null; then
#   if [ -f "$HOME/.local/bin/aws" ]; then
#     export PATH="$HOME/.local/bin:$PATH"
#   elif [ -f "/usr/local/bin/aws" ]; then
#     export PATH="/usr/local/bin:$PATH"
#   fi
# fi

ENVIRONMENT=${1:-dev}
AWS_REGION=${AWS_REGION:-ca-central-1}

# Store the root directory before changing
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

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

cd "$ROOT_DIR/infra/terraform"

# Check if backend already exists
BUCKET_NAME="artguard-terraform-state"
STATE_KEY="$ENVIRONMENT/terraform.tfstate"

echo ""
echo "🔍 Checking existing infrastructure..."

# Try to check backend using Python (more reliable than AWS CLI)
if command -v python3 &> /dev/null; then
  python3 -c "
import boto3
import sys
s3 = boto3.client('s3', region_name='$AWS_REGION')
try:
    s3.head_bucket(Bucket='$BUCKET_NAME')
    print('⚠️  S3 bucket already exists: $BUCKET_NAME')
except:
    print('✅ S3 bucket does not exist yet')
try:
    s3.head_object(Bucket='$BUCKET_NAME', Key='$STATE_KEY')
    print('⚠️  State file already exists: $STATE_KEY')
    print('⚠️  This environment may already be bootstrapped')
    sys.exit(1)
except:
    print('✅ State file does not exist yet')
" 2>/dev/null || {
    echo ""
    read -p "Continue anyway? (yes/no): " CONTINUE
    if [ "$CONTINUE" != "yes" ]; then
      echo "❌ Aborted"
      exit 1
    fi
  }
else
  # Fallback: skip checks if Python not available
  echo "⚠️  Python3 not available, skipping backend checks"
  echo "   Will attempt to create backend if needed"
fi

# Setup backend (S3 + DynamoDB)
echo ""
echo "Setting up backend..."
# Try Python script first (works even if AWS CLI is broken)
# From infra/terraform, scripts are at ../../scripts/
if [ -f "../../scripts/setup-backend.py" ]; then
  echo "Using Python backend setup script..."
  python3 ../../scripts/setup-backend.py
elif [ -f "../scripts/setup-backend.py" ]; then
  echo "Using Python backend setup script..."
  python3 ../scripts/setup-backend.py
elif [ -f "setup-backend.py" ]; then
  echo "Using Python backend setup script..."
  python3 setup-backend.py
elif [ -f "../../scripts/setup-backend.sh" ]; then
  chmod +x ../../scripts/setup-backend.sh
  ../../scripts/setup-backend.sh
elif [ -f "../scripts/setup-backend.sh" ]; then
  chmod +x ../scripts/setup-backend.sh
  ../scripts/setup-backend.sh
elif [ -f "setup-backend.sh" ]; then
  chmod +x setup-backend.sh
  ./setup-backend.sh
else
  echo "⚠️  No backend setup script found!"
  echo "   Please create the backend manually:"
  echo "   1. S3 bucket: artguard-terraform-state"
  echo "   2. DynamoDB table: artguard-terraform-locks"
  echo ""
  read -p "Continue anyway? (yes/no): " CONTINUE
  if [ "$CONTINUE" != "yes" ]; then
    echo "❌ Aborted"
    exit 1
  fi
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
# Check if tfvars file exists in current directory, parent, or root
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
