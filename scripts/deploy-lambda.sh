#!/bin/bash
set -e

# Deploy Lambda Functions
# Usage: ./deploy-lambda.sh [environment]
# Example: ./deploy-lambda.sh dev

ENVIRONMENT=${1:-dev}
AWS_REGION=${AWS_REGION:-ca-central-1}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Deploying Lambda Functions"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Environment: $ENVIRONMENT"
echo "Region: $AWS_REGION"
echo ""

cd infra/lambda

# 1. Package and deploy image_processor
echo "Packaging image_processor Lambda..."
cd image_processor

# Clean previous builds
rm -rf package image_processor.zip 2>/dev/null || true
mkdir -p package

# Install dependencies if requirements.txt exists
if [ -f requirements.txt ]; then
  echo "  Installing Python dependencies..."
  pip install -r requirements.txt -t package/ --quiet
fi

# Copy Lambda code
cp lambda_function.py package/

# Create ZIP
cd package
zip -r ../image_processor.zip . > /dev/null
cd ..

echo "✅ Package created: image_processor.zip"

# Update Lambda function
echo "Updating Lambda function..."
aws lambda update-function-code \
  --function-name artguard-image-processor \
  --zip-file fileb://image_processor.zip \
  --region $AWS_REGION \
  --no-cli-pager > /dev/null

echo "✅ image_processor deployed!"

# 2. Package and deploy ecs_scheduler
cd ../ecs_scheduler
echo ""
echo "Packaging ecs_scheduler Lambda..."

# Clean previous builds
rm -rf package ecs_scheduler.zip 2>/dev/null || true
mkdir -p package

# Copy Lambda code
cp lambda_function.py package/

# Create ZIP
cd package
zip -r ../ecs_scheduler.zip . > /dev/null
cd ..

echo "✅ Package created: ecs_scheduler.zip"

# Update Lambda function
echo "🔄 Updating Lambda function..."
aws lambda update-function-code \
  --function-name artguard-ecs-scheduler \
  --zip-file fileb://ecs_scheduler.zip \
  --region $AWS_REGION \
  --no-cli-pager > /dev/null

echo "✅ ecs_scheduler deployed!"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Lambda Deployment Complete"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Environment: $ENVIRONMENT"
echo ""
echo "Deployed functions:"
echo "  ✅ artguard-image-processor"
echo "  ✅ artguard-ecs-scheduler"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
