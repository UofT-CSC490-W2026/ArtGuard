#!/usr/bin/env bash
set -euo pipefail

# Destroy ArtGuard Infrastructure
#
# Usage:
#   ./scripts/destroy-all.sh [environment]                  # Destroys everything (default)
#   ./scripts/destroy-all.sh [environment] --preserve-data  # DR demo: orphans data, destroys stateless infra
#
# Default: destroys ALL resources including S3 data and DynamoDB tables.
#   S3 buckets have force_destroy=true in Terraform, so Terraform empties them automatically.
# --preserve-data: detaches data resources from Terraform state so they survive in AWS as
#   orphans, then destroys all stateless infrastructure. Run recover-prod.sh to restore.

source "$(dirname "$0")/_colors.sh"

ENVIRONMENT=${1:-dev}
PRESERVE_DATA=${2:-}
AWS_REGION=${AWS_REGION:-ca-central-1}
TERRAFORM_DIR="infra/terraform"
PROJECT_NAME="artguard"

header "Destroy ArtGuard Resources"
echo -e "  Environment: ${CYAN}$ENVIRONMENT${NC}"
echo -e "  Region:      ${CYAN}$AWS_REGION${NC}"
echo ""

if [[ "$PRESERVE_DATA" == "--preserve-data" ]]; then
  echo -e "${YELLOW}MODE: Data-preserving (disaster recovery simulation)${NC}"
  echo ""
  info "The following will SURVIVE as AWS orphans:"
  echo -e "  ${GREEN}DynamoDB:${NC} ${PROJECT_NAME}-{users,inference-records,image-records,patch-records,run-records,config-records}-${ENVIRONMENT}"
  echo -e "  ${GREEN}S3:${NC}       ${PROJECT_NAME}-images-raw-${ENVIRONMENT}"
  echo -e "  ${GREEN}S3:${NC}       ${PROJECT_NAME}-knowledge-base-${ENVIRONMENT}"
  echo ""
  warn "All stateless infra (ECS, ALB, VPC, CloudFront, OpenSearch, Bedrock KB) will be destroyed."
  echo -e "  Run ${CYAN}./scripts/recover-prod.sh $ENVIRONMENT${NC} to restore."
  echo ""
  read -rp "Type DESTROY to confirm: " CONFIRM
else
  echo -e "${RED}MODE: Full destruction — ALL data will be permanently deleted.${NC}"
  echo ""
  error "This will permanently delete all AWS resources."
  echo -e "  ${DIM}S3 data, DynamoDB records, OpenSearch vectors — everything.${NC}"
  echo ""
  read -p "Type DESTROY to confirm: " CONFIRM
fi

if [[ "$CONFIRM" != "DESTROY" ]]; then
  error "Aborted."
  exit 1
fi
echo ""

cd "$TERRAFORM_DIR"

if [[ "$PRESERVE_DATA" == "--preserve-data" ]]; then
  step "[1/2] Detaching data resources from Terraform state..."
  DATA_RESOURCES=(
    "aws_dynamodb_table.users"
    "aws_dynamodb_table.inference_records"
    "aws_dynamodb_table.image_records"
    "aws_dynamodb_table.patch_records"
    "aws_dynamodb_table.run_records"
    "aws_dynamodb_table.config_records"
    "aws_s3_bucket.images_raw"
    "aws_s3_bucket_versioning.images_raw"
    "aws_s3_bucket_server_side_encryption_configuration.images_raw"
    "aws_s3_bucket_public_access_block.images_raw"
    "aws_s3_bucket_lifecycle_configuration.images_raw"
    "aws_s3_bucket_policy.images_raw"
    "aws_s3_bucket_metric.images_raw"
    "aws_s3_bucket.knowledge_base"
    "aws_s3_bucket_versioning.knowledge_base"
    "aws_s3_bucket_server_side_encryption_configuration.knowledge_base"
    "aws_s3_bucket_public_access_block.knowledge_base"
    "aws_s3_bucket_metric.knowledge_base"
  )
  for resource in "${DATA_RESOURCES[@]}"; do
    if terraform state show "$resource" &>/dev/null; then
      terraform state rm "$resource"
      success "Detached: $resource"
    else
      echo -e "  ${DIM}Not in state (skipping): $resource${NC}"
    fi
  done
  echo ""
fi

step "[2/2] Cleaning up secrets before destroy..."
for secret_suffix in "modal-api-key" "jwt-secret"; do
  secret_name="${PROJECT_NAME}/${secret_suffix}-${ENVIRONMENT}"
  aws secretsmanager restore-secret \
    --secret-id "$secret_name" \
    --region "$AWS_REGION" 2>/dev/null && warn "Restored pending-deletion: $secret_name"
  aws secretsmanager delete-secret \
    --secret-id "$secret_name" \
    --force-delete-without-recovery \
    --region "$AWS_REGION" 2>/dev/null \
    && success "Deleted: $secret_name" \
    || echo -e "  ${DIM}Not found (already deleted): $secret_name${NC}"
  tf_resource="aws_secretsmanager_secret.${secret_suffix//-/_}"
  tf_version="aws_secretsmanager_secret_version.${secret_suffix//-/_}"
  terraform state rm "$tf_resource" 2>/dev/null || true
  terraform state rm "$tf_version" 2>/dev/null || true
done
echo ""

step "Disabling ALB deletion protection..."
ALB_ARN=$(aws elbv2 describe-load-balancers \
  --names "${PROJECT_NAME}-backend-alb" \
  --region "$AWS_REGION" \
  --query 'LoadBalancers[0].LoadBalancerArn' --output text 2>/dev/null) || true
if [[ -n "$ALB_ARN" && "$ALB_ARN" != "None" ]]; then
  aws elbv2 modify-load-balancer-attributes \
    --load-balancer-arn "$ALB_ARN" \
    --attributes Key=deletion_protection.enabled,Value=false \
    --region "$AWS_REGION" 2>/dev/null \
    && success "ALB deletion protection disabled" \
    || echo -e "  ${DIM}Could not modify ALB (may already be deleted)${NC}"
else
  echo -e "  ${DIM}ALB not found (already deleted)${NC}"
fi
echo ""

step "Updating force_destroy settings..."
terraform apply -var-file="${ENVIRONMENT}.tfvars" -auto-approve \
  -target=aws_s3_bucket.frontend \
  -target=aws_s3_bucket.images_raw \
  -target=aws_s3_bucket.images_processed \
  -target=aws_s3_bucket.knowledge_base \
  -target=aws_ecr_repository.backend \
  -target=aws_lb.backend \
  2>/dev/null || true
echo ""

step "Running terraform destroy..."
set +e
if ! terraform destroy -var-file="${ENVIRONMENT}.tfvars"; then
  echo ""
  warn "Some resources may still be cleaning up (e.g. OpenSearch ENIs). Retrying in 60s..."
  sleep 60
  terraform destroy -var-file="${ENVIRONMENT}.tfvars" -auto-approve
fi
set -e

echo ""
if [[ "$PRESERVE_DATA" == "--preserve-data" ]]; then
  header "Destroy Complete (data preserved)"
  success "Data resources survive as AWS orphans."
  echo -e "  To restore: ${CYAN}./scripts/recover-prod.sh $ENVIRONMENT${NC}"
else
  header "Destroy Complete"
  success "All resources deleted."
  echo -e "  To redeploy: ${CYAN}./scripts/deploy-all.sh $ENVIRONMENT${NC}"
fi
