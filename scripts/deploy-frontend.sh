#!/bin/bash
set -e

source "$(dirname "$0")/_colors.sh"

# Build and deploy Vite frontend to S3 + CloudFront
# Usage: ./deploy-frontend.sh [environment]
# Example:
#   export VITE_API_URL=https://dxxxx.cloudfront.net
#   (Same CloudFront URL as the site; API paths /auth, /inference, etc. are routed to the ALB.)
#   ./scripts/deploy-frontend.sh dev
#
# VITE_API_URL is required (baked in at build time). No trailing slash.
# Use the same https://...cloudfront.net origin as the UI so API calls stay HTTPS (no mixed content).
#
# Optional: CLOUDFRONT_DISTRIBUTION_ID=E123... if Terraform is unavailable (skips auto lookup).

ENVIRONMENT=${1:-dev}
AWS_REGION=${AWS_REGION:-ca-central-1}
FRONTEND_DIR="src/apps/frontend"
BUCKET_NAME="artguard-frontend-$ENVIRONMENT"
DIST_DIR="dist"

header "Building and Deploying Frontend (Vite)"
echo -e "  Environment: ${CYAN}$ENVIRONMENT${NC}"
echo -e "  Region:      ${CYAN}$AWS_REGION${NC}"
echo -e "  Bucket:      ${CYAN}$BUCKET_NAME${NC}"
echo ""

# ─── Validate VITE_API_URL ────────────────────────────────────────────────────
if [ -z "${VITE_API_URL:-}" ]; then
  error "VITE_API_URL is not set. It is compiled into the bundle at build time."
  echo -e "  Example:"
  echo -e "    ${GREEN}export VITE_API_URL=\$(terraform -chdir=infra/terraform output -raw cloudfront_distribution_url)${NC}"
  echo -e "  ${DIM}Or point at your ALB URL if the browser calls the API directly.${NC}"
  echo -e "  ${DIM}Do not use a trailing slash.${NC}"
  exit 1
fi

info "VITE_API_URL: ${BOLD}$VITE_API_URL${NC}"
echo ""

# ─── Resolve paths from repo root ────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_ABS="$REPO_ROOT/$FRONTEND_DIR"

if [ ! -d "$FRONTEND_ABS" ]; then
  error "Frontend directory not found: $FRONTEND_ABS"
  exit 1
fi

cd "$FRONTEND_ABS"

# ─── Build ────────────────────────────────────────────────────────────────────
step "Cleaning previous builds..."
rm -rf "$DIST_DIR" node_modules/.cache 2>/dev/null || true

step "Installing dependencies..."
npm ci --quiet

step "Building Vite production bundle..."
export NODE_ENV=production
npm run build

if [ ! -d "$DIST_DIR" ]; then
  error "'$DIST_DIR' directory not found after build."
  exit 1
fi

if [ ! -f "$DIST_DIR/index.html" ]; then
  error "index.html not found in build output."
  exit 1
fi

success "Build complete!"
echo ""

# ─── Deploy to S3 ────────────────────────────────────────────────────────────
step "Deploying to S3..."

# Static assets (JS, CSS, images) — long cache, content-hashed filenames
info "Syncing static assets with long cache (1 year, immutable)..."
aws s3 sync "$DIST_DIR/" "s3://$BUCKET_NAME/" \
  --delete \
  --cache-control "public, max-age=31536000, immutable" \
  --exclude "*.html" \
  --exclude "*.json" \
  --exclude "*.txt" \
  --exclude "*.xml" \
  --region "$AWS_REGION"

# HTML and metadata — short cache, must-revalidate so CloudFront checks origin
info "Syncing HTML and metadata with short cache (must-revalidate)..."
aws s3 sync "$DIST_DIR/" "s3://$BUCKET_NAME/" \
  --cache-control "public, max-age=0, must-revalidate" \
  --exclude "*" \
  --include "*.html" \
  --include "*.json" \
  --include "*.txt" \
  --include "*.xml" \
  --region "$AWS_REGION"

success "S3 deployment complete!"

# ─── CloudFront invalidation ─────────────────────────────────────────────────
echo ""
step "Invalidating CloudFront cache..."

# Try to resolve the distribution ID: env var → Terraform output → AWS API lookup
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
  warn "Could not find CloudFront distribution ID (cache not invalidated)."
  echo -e "  Set ${CYAN}CLOUDFRONT_DISTRIBUTION_ID${NC}, or run from repo with Terraform state:"
  echo -e "    ${GREEN}export CLOUDFRONT_DISTRIBUTION_ID=\$(terraform -chdir=infra/terraform output -raw cloudfront_distribution_id)${NC}"
  echo -e "  Or invalidate manually:"
  echo -e "    ${DIM}aws cloudfront create-invalidation --distribution-id \"\$ID\" --paths \"/*\" --region us-east-1${NC}"
else
  info "Distribution ID: ${BOLD}$DISTRIBUTION_ID${NC}"
  INVALIDATION_ID=$(aws cloudfront create-invalidation \
    --distribution-id "$DISTRIBUTION_ID" \
    --paths "/*" \
    --query 'Invalidation.Id' \
    --output text \
    --region us-east-1)
  success "Invalidation created: $INVALIDATION_ID"
  echo -e "  ${DIM}Cache invalidation typically takes 1-5 minutes.${NC}"
fi

echo ""
header "Frontend Deployment Complete"
echo -e "  Environment: ${CYAN}$ENVIRONMENT${NC}"
echo -e "  S3 Bucket:   ${CYAN}$BUCKET_NAME${NC}"
echo ""
info "Your frontend will be live in ~2-5 minutes."
