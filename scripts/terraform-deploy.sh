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

source "$(dirname "$0")/_colors.sh"

ENVIRONMENT=${1:-dev}
ACTION=${2:-plan}
AWS_REGION=${AWS_REGION:-ca-central-1}
TERRAFORM_DIR="infra/terraform"

cd $TERRAFORM_DIR

header "Terraform Deployment"
echo -e "  Environment:    ${CYAN}$ENVIRONMENT${NC}"
echo -e "  Action:         ${BOLD}$ACTION${NC}"
echo -e "  Region:         ${CYAN}$AWS_REGION${NC}"
echo -e "  Backend Config: ${CYAN}backend-$ENVIRONMENT.hcl${NC}"
echo -e "  Variables File: ${CYAN}$ENVIRONMENT.tfvars${NC}"
echo ""

case $ACTION in
  init)
    step "Initializing Terraform..."
    terraform init -backend-config=backend-$ENVIRONMENT.hcl
    success "Terraform initialized!"
    ;;

  plan)
    step "Creating Terraform plan..."
    terraform plan -var-file=$ENVIRONMENT.tfvars -out=tfplan
    echo ""
    success "Plan created successfully!"
    echo "Plan saved to: tfplan"
    echo ""
    echo -e "To apply this plan, run:"
    echo -e "  ${GREEN}./scripts/terraform-deploy.sh $ENVIRONMENT apply${NC}"
    ;;

  apply)
    if [ -f "tfplan" ]; then
      step "Applying saved plan..."
      terraform apply tfplan
      rm tfplan
    else
      warn "No saved plan found. Creating and applying..."
      terraform apply -var-file=$ENVIRONMENT.tfvars -auto-approve
    fi

    echo ""
    header "Terraform Deployment Complete"
    echo ""
    info "Key Outputs:"
    echo ""
    echo -e "  ${BOLD}Frontend:${NC}"
    terraform output cloudfront_distribution_url || echo -e "  ${DIM}Not available${NC}"
    echo ""
    echo -e "  ${BOLD}Backend API:${NC}"
    terraform output backend_url || echo -e "  ${DIM}Not available${NC}"
    terraform output alb_dns_name || echo -e "  ${DIM}Not available${NC}"
    echo ""
    echo -e "  ${BOLD}ECS:${NC}"
    terraform output ecs_cluster_name || echo -e "  ${DIM}Not available${NC}"
    terraform output ecs_service_name || echo -e "  ${DIM}Not available${NC}"
    ;;

  destroy)
    echo -e "${RED}DESTRUCTIVE ACTION: This will destroy all infrastructure!${NC}"
    echo -e "Environment: ${CYAN}$ENVIRONMENT${NC}"
    echo ""
    read -p "Type 'yes' to confirm: " CONFIRM

    if [ "$CONFIRM" != "yes" ]; then
      error "Aborted"
      exit 1
    fi

    echo ""
    step "Destroying infrastructure..."
    terraform destroy -var-file=$ENVIRONMENT.tfvars -auto-approve
    success "Infrastructure destroyed"
    ;;

  *)
    error "Invalid action: $ACTION"
    echo ""
    echo -e "Usage: ${CYAN}./terraform-deploy.sh [environment] [action]${NC}"
    echo ""
    echo "Actions:"
    echo -e "  ${GREEN}init${NC}    - Initialize Terraform backend"
    echo -e "  ${GREEN}plan${NC}    - Create execution plan"
    echo -e "  ${GREEN}apply${NC}   - Apply changes"
    echo -e "  ${RED}destroy${NC} - Destroy all infrastructure"
    echo ""
    echo "Examples:"
    echo -e "  ${DIM}./terraform-deploy.sh dev init${NC}"
    echo -e "  ${DIM}./terraform-deploy.sh dev plan${NC}"
    echo -e "  ${DIM}./terraform-deploy.sh dev apply${NC}"
    exit 1
    ;;
esac
