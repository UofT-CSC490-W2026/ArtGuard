#!/bin/bash
set -e

# Build and Push Docker Image to ECR
# Usage: ./build-and-push-docker.sh [environment]
# Example: ./build-and-push-docker.sh dev

source "$(dirname "$0")/_colors.sh"

ENVIRONMENT=${1:-dev}
AWS_REGION=${AWS_REGION:-ca-central-1}
ECR_REPOSITORY=${ECR_REPOSITORY:-artguard-backend}

header "Building and Pushing Docker Image"
echo -e "  Environment: ${CYAN}$ENVIRONMENT${NC}"
echo -e "  Region:      ${CYAN}$AWS_REGION${NC}"
echo -e "  Repository:  ${CYAN}$ECR_REPOSITORY${NC}"
echo ""

# Generate image tag
DATE_TAG=$(date +%Y.%m.%d)
SHORT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "local")
BUILD_NUMBER=${GITHUB_RUN_NUMBER:-$(date +%s)}
IMAGE_TAG="v${DATE_TAG}-${SHORT_SHA}-${BUILD_NUMBER}"

info "Image tag: ${BOLD}$IMAGE_TAG${NC}"
echo ""

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

step "Logging into ECR..."
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $ECR_REGISTRY

echo ""
step "Building Docker image..."
docker build \
  --platform linux/amd64 \
  --build-arg ENVIRONMENT=$ENVIRONMENT \
  -t $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG \
  -t $ECR_REGISTRY/$ECR_REPOSITORY:latest \
  -f Dockerfile \
  .

echo ""
step "Pushing to ECR..."
docker push $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
docker push $ECR_REGISTRY/$ECR_REPOSITORY:latest

echo ""
header "Image Pushed Successfully"
success "Image:  $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG"
success "Latest: $ECR_REGISTRY/$ECR_REPOSITORY:latest"
echo ""
echo -e "To deploy to ECS, run:"
echo -e "  ${GREEN}./scripts/deploy-ecs.sh $ENVIRONMENT${NC}"
