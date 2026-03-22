#!/bin/bash
set -e

# Force ECS Service Deployment
# Usage: ./deploy-ecs.sh [environment]
# Example: ./deploy-ecs.sh dev

source "$(dirname "$0")/_colors.sh"

export AWS_PAGER=""

ENVIRONMENT=${1:-dev}
AWS_REGION=${AWS_REGION:-ca-central-1}
ECS_CLUSTER=${ECS_CLUSTER:-artguard-cluster}
ECS_SERVICE=${ECS_SERVICE:-artguard-backend}

header "Deploying ECS Service"
echo -e "  Environment: ${CYAN}$ENVIRONMENT${NC}"
echo -e "  Region:      ${CYAN}$AWS_REGION${NC}"
echo -e "  Cluster:     ${CYAN}$ECS_CLUSTER${NC}"
echo -e "  Service:     ${CYAN}$ECS_SERVICE${NC}"
echo ""

step "Forcing new deployment..."
aws ecs update-service \
  --cluster $ECS_CLUSTER \
  --service $ECS_SERVICE \
  --force-new-deployment \
  --region $AWS_REGION

echo ""
header "Deployment Initiated"
success "ECS will perform a rolling deployment:"
echo -e "  ${DIM}1. Start new tasks with latest image${NC}"
echo -e "  ${DIM}2. Wait for health checks to pass${NC}"
echo -e "  ${DIM}3. Drain and stop old tasks${NC}"
echo ""
info "Expected time: ~2-3 minutes"
echo ""
echo -e "Monitor deployment:"
echo -e "  ${GREEN}./scripts/ecs-control.sh status $ENVIRONMENT${NC}"
