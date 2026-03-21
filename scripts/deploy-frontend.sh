#!/bin/bash
set -e

# Build and deploy Vite frontend to S3 + CloudFront
# Usage: ./deploy-frontend.sh [environment]
# Example:
#   export VITE_API_URL=https://dxxxx.cloudfront.net
#   (Same CloudFront URL as the site; API paths /auth, /inference, etc. are routed to the ALB.)
#   ./scripts/deploy-frontend.sh dev
#
# VITE_API_URL is required (baked in at build time). No trailing slash.
# Use the same https://…cloudfront.net origin as the UI so API calls stay HTTPS (no mixed content).
#
# Optional: CLOUDFRONT_DISTRIBUTION_ID=E123... if Terraform is unavailable (skips auto lookup).

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
  echo "     export VITE_API_URL=\$(terraform -chdir=infra/terraform output -raw cloudfront_distribution_url)"
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

# Resolve distribution ID (JMESPath contains(Origins.Items[].DomainName, ...) is invalid — use terraform / jq)
DISTRIBUTION_ID="${CLOUDFRONT_DISTRIBUTION_ID:-}"
if [ -z "$DISTRIBUTION_ID" ] && command -v terraform >/dev/null 2>&1; then
  DISTRIBUTION_ID=$(terraform -chdir="$REPO_ROOT/infra/terraform" output -raw cloudfront_distribution_id 2>/dev/null) || true
fi
if [ -z "$DISTRIBUTION_ID" ]; then
  if command -v jq >/dev/null 2>&1; then
    DISTRIBUTION_ID=$(aws cloudfront list-distributions --output json --region us-east-1 \
      | jq -r --arg b "$BUCKET_NAME" '
          .DistributionList.Items[]?
          | select(any(.Origins.Items[]?; .DomainName | contains($b)))
          | .Id' 2>/dev/null | head -n 1)
  fi
fi

if [ -z "$DISTRIBUTION_ID" ]; then
  echo "⚠️  Warning: Could not find CloudFront distribution ID (cache not invalidated)."
  echo "   Set CLOUDFRONT_DISTRIBUTION_ID, or run from repo with Terraform state:"
  echo "     export CLOUDFRONT_DISTRIBUTION_ID=\$(terraform -chdir=infra/terraform output -raw cloudfront_distribution_id)"
  echo "   Then re-run this script, or invalidate manually:"
  echo "     aws cloudfront create-invalidation --distribution-id \"\$CLOUDFRONT_DISTRIBUTION_ID\" --paths \"/*\" --region us-east-1"
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
