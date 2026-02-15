#!/bin/bash
set -e

# Force ECS Service Deployment
# Usage: ./deploy-ecs.sh [environment]
# Example: ./deploy-ecs.sh dev

ENVIRONMENT=${1:-dev}
AWS_REGION=${AWS_REGION:-ca-central-1}
ECS_CLUSTER=${ECS_CLUSTER:-artguard-cluster}
ECS_SERVICE=${ECS_SERVICE:-artguard-backend}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Deploying ECS Service"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Environment: $ENVIRONMENT"
echo "Region: $AWS_REGION"
echo "Cluster: $ECS_CLUSTER"
echo "Service: $ECS_SERVICE"
echo ""

echo "Forcing new deployment..."
aws ecs update-service \
  --cluster $ECS_CLUSTER \
  --service $ECS_SERVICE \
  --force-new-deployment \
  --region $AWS_REGION \
  --no-cli-pager

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Deployment Initiated"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "ECS will perform a rolling deployment:"
echo "  1. Start new tasks with latest image"
echo "  2. Wait for health checks to pass"
echo "  3. Drain and stop old tasks"
echo ""
echo "Expected time: ~2-3 minutes"
echo ""
echo "Monitor deployment:"
echo "   ./scripts/ecs-control.sh status $ENVIRONMENT"
echo "   or"
echo "   aws ecs describe-services --cluster $ECS_CLUSTER --services $ECS_SERVICE --region $AWS_REGION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
