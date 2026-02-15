#!/bin/bash
set -e

# Build and Deploy Frontend to S3 + CloudFront
# Usage: ./deploy-frontend.sh [environment]
# Example: ./deploy-frontend.sh dev

ENVIRONMENT=${1:-dev}
AWS_REGION=${AWS_REGION:-ca-central-1}
FRONTEND_DIR="src/apps/frontend"
BUCKET_NAME="artguard-frontend-$ENVIRONMENT"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Building and Deploying Frontend"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Environment: $ENVIRONMENT"
echo "Region: $AWS_REGION"
echo "Bucket: $BUCKET_NAME"
echo ""

# Check if frontend directory exists
if [ ! -d "$FRONTEND_DIR" ]; then
  echo "❌ Frontend directory not found: $FRONTEND_DIR"
  exit 1
fi

cd $FRONTEND_DIR

# Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -rf build node_modules/.cache 2>/dev/null || true

# Install dependencies
echo "Installing dependencies..."
npm ci --quiet

# Build React application
echo "Building React frontend..."
echo "  Environment: $ENVIRONMENT"

export NODE_ENV=production
export REACT_APP_ENVIRONMENT=$ENVIRONMENT

npm run build

# Verify build output
if [ ! -d "build" ]; then
  echo "❌ Error: 'build' directory not found after build"
  exit 1
fi

if [ ! -f "build/index.html" ]; then
  echo "❌ Error: index.html not found in build output"
  exit 1
fi

echo "✅ Build complete!"
echo ""

# Deploy to S3
echo "Deploying to S3..."
echo "  Step 1: Syncing static assets with long cache..."
aws s3 sync build/ s3://$BUCKET_NAME/ \
  --delete \
  --cache-control "public, max-age=31536000, immutable" \
  --exclude "*.html" \
  --exclude "*.json" \
  --exclude "*.txt" \
  --exclude "*.xml" \
  --region $AWS_REGION

echo "  Step 2: Syncing HTML and metadata with short cache..."
aws s3 sync build/ s3://$BUCKET_NAME/ \
  --cache-control "public, max-age=0, must-revalidate" \
  --exclude "*" \
  --include "*.html" \
  --include "*.json" \
  --include "*.txt" \
  --include "*.xml" \
  --region $AWS_REGION

echo "✅ S3 deployment complete!"

# Invalidate CloudFront cache
echo ""
echo "Invalidating CloudFront cache..."

# Get CloudFront distribution ID
DISTRIBUTION_ID=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?contains(Origins.Items[].DomainName, '$BUCKET_NAME')].Id" \
  --output text \
  --region us-east-1 \
  | head -n 1)

if [ -z "$DISTRIBUTION_ID" ]; then
  echo "⚠️  Warning: Could not find CloudFront distribution ID"
  echo "   Manual cache invalidation may be required"
else
  echo "  Distribution ID: $DISTRIBUTION_ID"

  INVALIDATION_ID=$(aws cloudfront create-invalidation \
    --distribution-id $DISTRIBUTION_ID \
    --paths "/*" \
    --query 'Invalidation.Id' \
    --output text \
    --region us-east-1)

  echo "✅ Invalidation created: $INVALIDATION_ID"
  echo "Cache invalidation typically takes 1-5 minutes"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Frontend Deployment Complete"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Environment: $ENVIRONMENT"
echo "S3 Bucket: $BUCKET_NAME"
echo ""
echo "Your frontend will be live in ~2-5 minutes"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
