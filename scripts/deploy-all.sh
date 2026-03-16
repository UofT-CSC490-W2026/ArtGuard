#!/usr/bin/env bash
set -euo pipefail

# Deploy All ArtGuard Resources from Scratch
# Usage: ./scripts/deploy-all.sh [environment]
# Example: ./scripts/deploy-all.sh dev
#
# Prerequisites:
#   - AWS CLI v2 configured (aws configure)
#   - Terraform >= 1.10.0
#   - Docker Desktop running
#   - Python 3.11+
#   - awscurl (pip install awscurl)
#   - jq (brew install jq)
#   - Modal API key ready
#   - Pipeline output files in src/apps/data_pipeline/output/

ENVIRONMENT=${1:-dev}
AWS_REGION=${AWS_REGION:-ca-central-1}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "ArtGuard Full Deployment"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Environment: $ENVIRONMENT"
echo "Region:      $AWS_REGION"
echo ""

# ─── Step 1: Bootstrap Infrastructure (~15-20 min) ───
echo "━━━ Step 1/6: Bootstrap Infrastructure ━━━"
echo "This creates all AWS resources (VPC, ECS, S3, DynamoDB, OpenSearch, Bedrock KB, etc.)"
echo ""
./scripts/bootstrap.sh "$ENVIRONMENT"
echo ""

# ─── Step 2: Store Secrets ───
echo "━━━ Step 2/6: Store Secrets ━━━"
echo "You will be prompted for your Modal API key."
echo ""
./scripts/setup-secrets.sh "$ENVIRONMENT"
echo ""

# ─── Step 3: Build Docker Image (~5-10 min) ───
echo "━━━ Step 3/6: Build and Push Docker Image ━━━"
./scripts/build-and-push-docker.sh "$ENVIRONMENT"
echo ""

# ─── Step 4: Deploy to ECS (~2-3 min) ───
echo "━━━ Step 4/6: Deploy to ECS ━━━"
./scripts/deploy-ecs.sh "$ENVIRONMENT"
echo ""

# Wait for ECS to stabilize
BACKEND_URL=$(terraform -chdir=infra/terraform output -json summary | jq -r '.backend_url')
echo "Waiting for backend to become healthy..."
echo "URL: ${BACKEND_URL}/health"
MAX_RETRIES=20
RETRY=0
while [[ $RETRY -lt $MAX_RETRIES ]]; do
  HEALTH=$(curl -s "${BACKEND_URL}/health" 2>/dev/null || echo "unavailable")
  if echo "$HEALTH" | grep -q '"ok"'; then
    echo "Backend is healthy!"
    break
  fi
  RETRY=$((RETRY + 1))
  echo "  Attempt $RETRY/$MAX_RETRIES — not ready yet, retrying in 15 seconds..."
  sleep 15
done

if [[ $RETRY -eq $MAX_RETRIES ]]; then
  echo "ERROR: Backend did not become healthy after $((MAX_RETRIES * 15)) seconds."
  echo "Check logs: aws logs tail /ecs/artguard-backend --region $AWS_REGION --since 5m"
  exit 1
fi
echo ""

# ─── Step 5: Upload RAG Data and Ingest (~10-20 min) ───
echo "━━━ Step 5/6: Upload RAG Data ━━━"
echo "Converting JSONL to TXT and uploading to S3..."
./scripts/upload-rag-data.sh
echo ""

echo "Ingestion has been triggered. This takes ~10-20 minutes."
echo ""

# Get ingestion job info
KB_ID=$(terraform -chdir=infra/terraform output -raw knowledge_base_id)
DS_ID=$(aws bedrock-agent list-data-sources \
  --knowledge-base-id "$KB_ID" \
  --region "$AWS_REGION" \
  --query "dataSourceSummaries[0].dataSourceId" \
  --output text)
JOB_ID=$(aws bedrock-agent list-ingestion-jobs \
  --knowledge-base-id "$KB_ID" \
  --data-source-id "$DS_ID" \
  --region "$AWS_REGION" \
  --query "ingestionJobSummaries[0].ingestionJobId" \
  --output text)

echo "Waiting for ingestion to complete (checking every 30 seconds)..."
while true; do
  STATUS=$(aws bedrock-agent get-ingestion-job \
    --knowledge-base-id "$KB_ID" \
    --data-source-id "$DS_ID" \
    --ingestion-job-id "$JOB_ID" \
    --region "$AWS_REGION" \
    --query "ingestionJob.status" \
    --output text 2>/dev/null || echo "UNKNOWN")

  INDEXED=$(aws bedrock-agent get-ingestion-job \
    --knowledge-base-id "$KB_ID" \
    --data-source-id "$DS_ID" \
    --ingestion-job-id "$JOB_ID" \
    --region "$AWS_REGION" \
    --query "ingestionJob.statistics.numberOfNewDocumentsIndexed" \
    --output text 2>/dev/null || echo "0")

  echo "  Status: $STATUS | Documents indexed: $INDEXED"

  if [[ "$STATUS" == "COMPLETE" || "$STATUS" == "FAILED" || "$STATUS" == "STOPPED" ]]; then
    break
  fi
  sleep 30
done

echo ""
if [[ "$STATUS" == "COMPLETE" ]]; then
  echo "Ingestion complete!"
else
  echo "WARNING: Ingestion finished with status: $STATUS"
  echo "Check details:"
  echo "  aws bedrock-agent get-ingestion-job --knowledge-base-id $KB_ID --data-source-id $DS_ID --ingestion-job-id $JOB_ID --region $AWS_REGION"
fi
echo ""

# ─── Step 6: Verify ───
echo "━━━ Step 6/6: Verification ━━━"
echo ""

# Check vector count
ENDPOINT=$(terraform -chdir=infra/terraform output -raw opensearch_collection_endpoint)
echo "Vector count:"
awscurl --service aoss --region "$AWS_REGION" "${ENDPOINT}/bedrock-knowledge-base-index/_count" 2>/dev/null || echo "  Could not check vector count"
echo ""

# Health check
echo "Health check:"
curl -s "${BACKEND_URL}/health"
echo ""
echo ""

# RAG query test
echo "RAG query test:"
curl -s -X POST "${BACKEND_URL}/rag-query" \
  -H "Content-Type: application/json" \
  -d '{"query": "Tell me about Vincent van Gogh painting style"}' || echo "  RAG query failed — Anthropic model access may still be pending"
echo ""

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Deployment Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Backend URL: $BACKEND_URL"
echo ""
echo "Useful commands:"
echo "  curl ${BACKEND_URL}/health                    # Health check"
echo "  ./scripts/cost-control.sh pause               # Pause to save costs"
echo "  ./scripts/cost-control.sh resume              # Resume"
echo "  ./scripts/destroy-all.sh $ENVIRONMENT         # Tear down everything"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
