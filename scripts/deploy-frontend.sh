#!/bin/bash
set -e

# Build and deploy Vite frontend to S3 + CloudFront
# Usage: ./deploy-frontend.sh [environment]
# Example:
#   export VITE_API_URL=https://dxxxx.cloudfront.net/api
#   ./scripts/deploy-frontend.sh dev
#
# VITE_API_URL is required (baked in at build time). No trailing slash.
# If CloudFront serves the API under /api/*, include that path in the URL.

ENVIRONMENT=${1:-dev}
AWS_REGION=${AWS_REGION:-ca-central-1}
FRONTEND_DIR="src/apps/frontend"
BUCKET_NAME="artguard-frontend-$ENVIRONMENT"
DIST_DIR="dist"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Building and Deploying Frontend (Vite)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Environment: $ENVIRONMENT"
echo "Region: $AWS_REGION"
echo "Bucket: $BUCKET_NAME"
echo ""

if [ -z "${VITE_API_URL:-}" ]; then
  echo "❌ VITE_API_URL is not set. It is compiled into the bundle at build time."
  echo "   Example:"
  echo "     export VITE_API_URL=https://\$(terraform -chdir=infra/terraform output -raw cloudfront_distribution_url)/api"
  echo "   Or point at your ALB URL if the browser calls the API directly."
  echo "   Do not use a trailing slash."
  exit 1
fi

echo "VITE_API_URL: $VITE_API_URL"
echo ""

# Resolve paths from repo root (where this script is usually run)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_ABS="$REPO_ROOT/$FRONTEND_DIR"

if [ ! -d "$FRONTEND_ABS" ]; then
  echo "❌ Frontend directory not found: $FRONTEND_ABS"
  exit 1
fi

cd "$FRONTEND_ABS"

echo "🧹 Cleaning previous builds..."
rm -rf "$DIST_DIR" node_modules/.cache 2>/dev/null || true

echo "Installing dependencies..."
npm ci --quiet

echo "Building Vite production bundle..."
export NODE_ENV=production
npm run build

if [ ! -d "$DIST_DIR" ]; then
  echo "❌ Error: '$DIST_DIR' directory not found after build"
  exit 1
fi

if [ ! -f "$DIST_DIR/index.html" ]; then
  echo "❌ Error: index.html not found in build output"
  exit 1
fi

echo "✅ Build complete!"
echo ""

echo "Deploying to S3..."
echo "  Step 1: Syncing static assets with long cache..."
aws s3 sync "$DIST_DIR/" "s3://$BUCKET_NAME/" \
  --delete \
  --cache-control "public, max-age=31536000, immutable" \
  --exclude "*.html" \
  --exclude "*.json" \
  --exclude "*.txt" \
  --exclude "*.xml" \
  --region "$AWS_REGION"

echo "  Step 2: Syncing HTML and metadata with short cache..."
aws s3 sync "$DIST_DIR/" "s3://$BUCKET_NAME/" \
  --cache-control "public, max-age=0, must-revalidate" \
  --exclude "*" \
  --include "*.html" \
  --include "*.json" \
  --include "*.txt" \
  --include "*.xml" \
  --region "$AWS_REGION"

echo "✅ S3 deployment complete!"

echo ""
echo "Invalidating CloudFront cache..."

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
    --distribution-id "$DISTRIBUTION_ID" \
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
