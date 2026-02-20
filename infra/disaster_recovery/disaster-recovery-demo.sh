#!/bin/bash
# Complete disaster recovery demonstration: Destroy and restore infrastructure
# Verifies all 5 requirements:
# 1. Data processing services / deployed applications
# 2. Database systems and their data
# 3. Configuration settings
# 4. Access controls and security settings
# 5. System functionality verification
# Usage: ./disaster-recovery-demo.sh [dev|prod]

set -e

ENVIRONMENT=${1:-prod}
AWS_REGION=${AWS_REGION:-ca-central-1}
TERRAFORM_DIR="../terraform"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Ensure AWS CLI is in PATH
if [ -d "$HOME/.local/bin" ]; then
  export PATH="$HOME/.local/bin:$PATH"
fi

# Disable AWS CLI pager
export AWS_PAGER=""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "DISASTER RECOVERY DEMONSTRATION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Environment: $ENVIRONMENT"
echo "Region: $AWS_REGION"
echo ""
echo "This demo will:"
echo "  1. Show current working infrastructure (all 5 components)"
echo "  2. Destroy ALL infrastructure"
echo "  3. Verify complete deletion"
echo "  4. Restore from Infrastructure as Code"
echo "  5. Verify all components are restored and functional"
echo ""
echo "⚠️  WARNING: This will DESTROY all infrastructure!"
echo ""
read -p "Press Enter to continue (Ctrl+C to cancel)..."
echo ""

cd "$TERRAFORM_DIR"

# Find tfvars file
if [ -f "$ENVIRONMENT.tfvars" ]; then
  TFVARS_FILE="$ENVIRONMENT.tfvars"
elif [ -f "../$ENVIRONMENT.tfvars" ]; then
  TFVARS_FILE="../$ENVIRONMENT.tfvars"
elif [ -f "$ROOT_DIR/$ENVIRONMENT.tfvars" ]; then
  TFVARS_FILE="$ROOT_DIR/$ENVIRONMENT.tfvars"
else
  echo "❌ Error: $ENVIRONMENT.tfvars not found"
  exit 1
fi

# ============================================================================
# PHASE 1: PRE-DISASTER - Show Working System
# ============================================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PHASE 1: PRE-DISASTER - SHOWING WORKING SYSTEM"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Step 1: Backup state file
echo "📦 Step 1.1: Backing up Terraform state..."
"$SCRIPT_DIR/backup-state.sh" "$ENVIRONMENT" 2>/dev/null || echo "   ⚠️  State backup skipped (may not be needed)"

# Step 2: Comprehensive verification of all components
echo ""
echo "🔍 Step 1.2: Verifying all infrastructure components..."
echo ""
"$SCRIPT_DIR/verify-all-components.sh" "$ENVIRONMENT"

echo ""
read -p "Press Enter to proceed with disaster (destruction)..."
echo ""

# ============================================================================
# PHASE 2: DISASTER - Destroy Everything
# ============================================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PHASE 2: DISASTER - DESTROYING ALL INFRASTRUCTURE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Clean up any secrets scheduled for deletion first
if command -v python3 &> /dev/null; then
  echo "🧹 Cleaning up secrets scheduled for deletion..."
  python3 "$ROOT_DIR/scripts/fix-secret.py" 2>/dev/null || echo "   No secrets to clean up"
fi

echo ""
echo "💥 Running terraform destroy..."
echo "   This will delete:"
echo "   - ECS clusters and services"
echo "   - DynamoDB tables"
echo "   - S3 buckets"
echo "   - Load balancers"
echo "   - Security groups"
echo "   - IAM roles and policies"
echo "   - Bedrock Knowledge Base"
echo "   - OpenSearch collections"
echo "   - Secrets Manager secrets"
echo "   - And all other infrastructure..."
echo ""

terraform destroy -var-file="$TFVARS_FILE" -auto-approve

# ============================================================================
# PHASE 3: VERIFY COMPLETE DELETION
# ============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PHASE 3: VERIFYING COMPLETE DELETION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "🔍 Verifying all resources are deleted..."
"$ROOT_DIR/scripts/verify-deletion.sh" "$ENVIRONMENT"

echo ""
read -p "Press Enter to proceed with recovery (restoration)..."
echo ""

# ============================================================================
# PHASE 4: RECOVERY - Restore from IaC
# ============================================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PHASE 4: RECOVERY - RESTORING FROM INFRASTRUCTURE AS CODE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "🔄 Restoring infrastructure from Terraform code..."
echo "   All resources will be recreated from:"
echo "   - infra/terraform/*.tf files"
echo "   - Configuration: $TFVARS_FILE"
echo ""

terraform apply -var-file="$TFVARS_FILE" -auto-approve

# ============================================================================
# PHASE 5: POST-RECOVERY VERIFICATION
# ============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PHASE 5: POST-RECOVERY VERIFICATION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "⏳ Waiting 30 seconds for services to stabilize..."
sleep 30

echo ""
echo "🔍 Verifying all components are restored..."
echo ""
"$SCRIPT_DIR/verify-all-components.sh" "$ENVIRONMENT"

# Restore secrets if needed
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "SECRET RESTORATION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ -z "$MODAL_API_KEY" ]; then
  echo "⚠️  MODAL_API_KEY not set. Skipping secret restoration."
  echo "   To restore manually:"
  echo "   export MODAL_API_KEY='your-key'"
  echo "   $SCRIPT_DIR/secret_recovery.sh $ENVIRONMENT"
else
  echo "🔑 Restoring secrets..."
  "$SCRIPT_DIR/secret_recovery.sh" "$ENVIRONMENT" 2>/dev/null || echo "   ⚠️  Secret restoration script not found or failed"
fi

# Final summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ DISASTER RECOVERY DEMO COMPLETE!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Infrastructure Outputs:"
terraform output -var-file="$TFVARS_FILE" summary 2>/dev/null || terraform output -var-file="$TFVARS_FILE" 2>/dev/null || echo "   ⚠️  No outputs available"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"



