#!/bin/bash
set -e

# Terraform Deployment Script
# Usage: ./terraform-deploy.sh [environment] [action]
# Actions: init, plan, apply, destroy
# Examples:
#   ./terraform-deploy.sh dev init
#   ./terraform-deploy.sh dev plan
#   ./terraform-deploy.sh dev apply
#   ./terraform-deploy.sh prod apply

# Ensure standard PATH directories are included
# export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$HOME/.local/bin:$PATH"

ENVIRONMENT=${1:-dev}
ACTION=${2:-plan}
AWS_REGION=${AWS_REGION:-ca-central-1}
TERRAFORM_DIR="infra/terraform"

cd $TERRAFORM_DIR

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🏗️  Terraform Deployment"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Environment: $ENVIRONMENT"
echo "Action: $ACTION"
echo "Region: $AWS_REGION"
echo "Backend Config: backend-$ENVIRONMENT.hcl"
echo "Variables File: $ENVIRONMENT.tfvars"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

case $ACTION in
  init)
    echo "Initializing Terraform..."
    terraform init -backend-config=backend-$ENVIRONMENT.hcl
    echo "✅ Terraform initialized!"
    ;;

  plan)
    echo "Creating Terraform plan..."
    terraform plan -var-file=$ENVIRONMENT.tfvars -out=tfplan
    echo ""
    echo "✅ Plan created successfully!"
    echo "Plan saved to: tfplan"
    echo ""
    echo "To apply this plan, run:"
    echo "   ./scripts/terraform-deploy.sh $ENVIRONMENT apply"
    ;;

  apply)
    if [ -f "tfplan" ]; then
      echo "✅ Applying saved plan..."
      terraform apply tfplan
      rm tfplan
    else
      echo "⚠️  No saved plan found. Creating and applying..."
      terraform apply -var-file=$ENVIRONMENT.tfvars -auto-approve
    fi

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "✅ Terraform Deployment Complete"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Key Outputs:"
    echo ""
    echo "Frontend:"
    terraform output cloudfront_distribution_url || echo "  CloudFront URL not available"
    echo ""
    echo "Backend API:"
    terraform output backend_url || echo "  Backend URL not available"
    terraform output alb_dns_name || echo "  ALB DNS not available"
    echo ""
    echo "ECS:"
    terraform output ecs_cluster_name || echo "  ECS cluster not available"
    terraform output ecs_service_name || echo "  ECS service not available"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    ;;

  destroy)
    echo "⚠️  DESTRUCTIVE ACTION: This will destroy all infrastructure!"
    echo "Environment: $ENVIRONMENT"
    echo ""
    read -p "Type 'yes' to confirm: " CONFIRM

    if [ "$CONFIRM" != "yes" ]; then
      echo "❌ Aborted"
      exit 1
    fi

    echo ""
    echo "Destroying infrastructure..."
    terraform destroy -var-file=$ENVIRONMENT.tfvars -auto-approve
    echo "✅ Infrastructure destroyed"
    ;;

  *)
    echo "❌ Invalid action: $ACTION"
    echo ""
    echo "Usage: ./terraform-deploy.sh [environment] [action]"
    echo ""
    echo "Actions:"
    echo "  init    - Initialize Terraform backend"
    echo "  plan    - Create execution plan"
    echo "  apply   - Apply changes"
    echo "  destroy - Destroy all infrastructure"
    echo ""
    echo "Examples:"
    echo "  ./terraform-deploy.sh dev init"
    echo "  ./terraform-deploy.sh dev plan"
    echo "  ./terraform-deploy.sh dev apply"
    exit 1
    ;;
esac
