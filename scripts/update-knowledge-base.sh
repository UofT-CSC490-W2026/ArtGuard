#!/bin/bash
set -e

# Update Bedrock Knowledge Base with Documents
# Usage: ./update-knowledge-base.sh [environment] [docs_directory]
# Example: ./update-knowledge-base.sh dev ./docs

ENVIRONMENT=${1:-dev}
DOCS_DIR=${2:-./docs}
AWS_REGION=${AWS_REGION:-ca-central-1}
BUCKET_NAME="artguard-knowledge-base-$ENVIRONMENT"
S3_PREFIX="documents/"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Updating Bedrock Knowledge Base"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Environment: $ENVIRONMENT"
echo "Docs Directory: $DOCS_DIR"
echo "S3 Bucket: $BUCKET_NAME"
echo "S3 Prefix: $S3_PREFIX"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if docs directory exists
if [ ! -d "$DOCS_DIR" ]; then
  echo "❌ Documents directory not found: $DOCS_DIR"
  echo ""
  echo "Please provide a valid directory containing your documentation files."
  echo "Supported formats: .txt, .md, .pdf, .docx"
  exit 1
fi

# Count documents
DOC_COUNT=$(find "$DOCS_DIR" -type f \( -name "*.txt" -o -name "*.md" -o -name "*.pdf" -o -name "*.docx" \) | wc -l | tr -d ' ')

if [ "$DOC_COUNT" -eq "0" ]; then
  echo "⚠️  No documents found in $DOCS_DIR"
  echo "   Looking for: .txt, .md, .pdf, .docx files"
  exit 1
fi

echo "Found $DOC_COUNT document(s) to upload"
echo ""

# Upload documents to S3
echo "Uploading documents to S3..."
aws s3 sync "$DOCS_DIR" "s3://$BUCKET_NAME/$S3_PREFIX" \
  --delete \
  --exclude ".*" \
  --include "*.txt" \
  --include "*.md" \
  --include "*.pdf" \
  --include "*.docx" \
  --region $AWS_REGION

echo "✅ Documents uploaded successfully!"

# Trigger ingestion (if Knowledge Base ID is available)
echo ""
echo "🔄 Triggering Knowledge Base ingestion..."

# Get Knowledge Base ID
KB_ID=$(aws bedrock-agent list-knowledge-bases \
  --query "knowledgeBaseSummaries[?name=='artguard-knowledge-base'].knowledgeBaseId" \
  --output text \
  --region $AWS_REGION \
  2>/dev/null | head -n 1)

if [ -z "$KB_ID" ]; then
  echo "⚠️  Could not find Knowledge Base ID"
  echo "   Documents are uploaded, but automatic ingestion cannot be triggered"
  echo "   Bedrock will sync automatically within ~5-10 minutes"
else
  echo "  Knowledge Base ID: $KB_ID"

  # Get Data Source ID
  DS_ID=$(aws bedrock-agent list-data-sources \
    --knowledge-base-id $KB_ID \
    --query "dataSourceSummaries[0].dataSourceId" \
    --output text \
    --region $AWS_REGION \
    2>/dev/null)

  if [ -z "$DS_ID" ]; then
    echo "⚠️  Could not find Data Source ID"
    echo "   Documents will be ingested automatically"
  else
    echo "  Data Source ID: $DS_ID"
    echo "  Starting ingestion job..."

    JOB_ID=$(aws bedrock-agent start-ingestion-job \
      --knowledge-base-id $KB_ID \
      --data-source-id $DS_ID \
      --query "ingestionJob.ingestionJobId" \
      --output text \
      --region $AWS_REGION \
      2>/dev/null)

    if [ -n "$JOB_ID" ]; then
      echo "✅ Ingestion job started: $JOB_ID"
      echo "Processing typically takes 2-10 minutes depending on document count"
    fi
  fi
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Knowledge Base Update Complete"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Documents uploaded: $DOC_COUNT"
echo "S3 Location: s3://$BUCKET_NAME/$S3_PREFIX"
echo ""
echo "📝 Next steps:"
echo "  - Wait 2-10 minutes for embeddings to be created"
echo "  - Test RAG queries via your application API"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
