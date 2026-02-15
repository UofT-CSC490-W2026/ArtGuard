#!/bin/bash
set -e

# Build and Push Docker Image to ECR
# Usage: ./build-and-push-docker.sh [environment]
# Example: ./build-and-push-docker.sh dev

ENVIRONMENT=${1:-dev}
AWS_REGION=${AWS_REGION:-ca-central-1}
ECR_REPOSITORY=${ECR_REPOSITORY:-artguard-backend}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Building and Pushing Docker Image"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Environment: $ENVIRONMENT"
echo "Region: $AWS_REGION"
echo "Repository: $ECR_REPOSITORY"
echo ""

# Generate image tag
DATE_TAG=$(date +%Y.%m.%d)
SHORT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "local")
BUILD_NUMBER=${GITHUB_RUN_NUMBER:-$(date +%s)}
IMAGE_TAG="v${DATE_TAG}-${SHORT_SHA}-${BUILD_NUMBER}"

echo "Image tag: $IMAGE_TAG"
echo ""

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "Logging into ECR..."
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $ECR_REGISTRY

echo ""
echo "Building Docker image..."
docker build \
  --platform linux/amd64 \
  --build-arg ENVIRONMENT=$ENVIRONMENT \
  -t $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG \
  -t $ECR_REGISTRY/$ECR_REPOSITORY:latest \
  -f Dockerfile \
  .

echo ""
echo "Pushing to ECR..."
docker push $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
docker push $ECR_REGISTRY/$ECR_REPOSITORY:latest

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Image Pushed Successfully"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Image: $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG"
echo "Latest: $ECR_REGISTRY/$ECR_REPOSITORY:latest"
echo ""
echo "To deploy to ECS, run:"
echo "   ./scripts/deploy-ecs.sh $ENVIRONMENT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
