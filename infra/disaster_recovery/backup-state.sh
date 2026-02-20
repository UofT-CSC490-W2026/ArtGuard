#!/bin/bash
# Backup Terraform state files from S3
# Usage: ./backup-state.sh [dev|prod]

set -e

ENVIRONMENT=${1:-dev}
AWS_REGION=${AWS_REGION:-ca-central-1}
BACKUP_DIR="./state-backups"
BUCKET="artguard-terraform-state"
STATE_KEY="${ENVIRONMENT}/terraform.tfstate"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Terraform State Backup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Environment: $ENVIRONMENT"
echo "Region: $AWS_REGION"
echo ""

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Download state file
BACKUP_FILE="${BACKUP_DIR}/terraform.tfstate.${ENVIRONMENT}.${TIMESTAMP}.json"
echo "Downloading state file..."
aws s3 cp "s3://${BUCKET}/${STATE_KEY}" "$BACKUP_FILE" --region "$AWS_REGION"

if [ $? -eq 0 ]; then
    echo "✅ State file backed up to: $BACKUP_FILE"
    
    # Also create a latest symlink/copy
    LATEST_FILE="${BACKUP_DIR}/terraform.tfstate.${ENVIRONMENT}.latest.json"
    cp "$BACKUP_FILE" "$LATEST_FILE"
    echo "✅ Latest backup: $LATEST_FILE"
    
    # Show file size
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "   Size: $SIZE"
else
    echo "❌ Failed to backup state file"
    exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Backup Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"




