#!/usr/bin/env bash
set -euo pipefail

# Destroy All AWS Resources
# Usage: ./scripts/destroy-all.sh [environment]
# Example: ./scripts/destroy-all.sh dev
#
# This removes ALL AWS resources except:
#   - Terraform state bucket (artguard-terraform-state)
#   - Terraform lock table (artguard-terraform-locks)
#   - Anthropic model access approval (account-level)

ENVIRONMENT=${1:-dev}
AWS_REGION=${AWS_REGION:-ca-central-1}
TERRAFORM_DIR="infra/terraform"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Destroy All ArtGuard Resources"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Environment: $ENVIRONMENT"
echo "Region:      $AWS_REGION"
echo ""
echo "WARNING: This will permanently delete all AWS resources."
echo "S3 data, DynamoDB records, OpenSearch vectors — everything."
echo ""
read -p "Type DESTROY to confirm: " CONFIRM
if [[ "$CONFIRM" != "DESTROY" ]]; then
  echo "Aborted."
  exit 1
fi
echo ""

# Step 1: Empty S3 buckets (Terraform can't delete non-empty buckets)
echo "[1/3] Emptying S3 buckets..."
python3 -c "
import boto3
s3 = boto3.resource('s3', region_name='$AWS_REGION')
buckets = [
    'artguard-images-raw-$ENVIRONMENT',
    'artguard-images-processed-$ENVIRONMENT',
    'artguard-knowledge-base-$ENVIRONMENT',
    'artguard-frontend-$ENVIRONMENT',
]
for bucket_name in buckets:
    try:
        bucket = s3.Bucket(bucket_name)
        bucket.object_versions.all().delete()
        print(f'  Emptied {bucket_name}')
    except Exception as e:
        print(f'  Skipped {bucket_name}: {e}')
"
echo ""

# Step 2: Force delete secrets (they have a recovery window that blocks recreation)
echo "[2/3] Deleting secrets..."
aws secretsmanager delete-secret \
  --secret-id "artguard/modal-api-key-$ENVIRONMENT" \
  --force-delete-without-recovery \
  --region "$AWS_REGION" 2>/dev/null && echo "  Deleted modal-api-key secret" || echo "  Secret not found (already deleted)"
echo ""

# Step 3: Terraform destroy
echo "[3/3] Running terraform destroy..."
cd "$TERRAFORM_DIR"
terraform destroy -var-file="${ENVIRONMENT}.tfvars"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Destroy Complete"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "To redeploy, run:"
echo "  ./scripts/bootstrap.sh $ENVIRONMENT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
