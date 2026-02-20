#!/bin/bash
# Verify infrastructure exists and is functioning
# Usage: ./verify-infrastructure.sh [dev|prod]

set -e

ENVIRONMENT=${1:-dev}
AWS_REGION=${AWS_REGION:-ca-central-1}
TERRAFORM_DIR="../terraform"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Infrastructure Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Environment: $ENVIRONMENT"
echo "Region: $AWS_REGION"
echo ""

cd "$TERRAFORM_DIR"

# Get outputs
BACKEND_URL=$(terraform output -var-file="${ENVIRONMENT}.tfvars" -raw backend_url 2>/dev/null || echo "")
FRONTEND_URL=$(terraform output -var-file="${ENVIRONMENT}.tfvars" -raw cloudfront_distribution_url 2>/dev/null || echo "")

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1. S3 Buckets"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
S3_BUCKETS=$(aws s3 ls --region "$AWS_REGION" 2>/dev/null | grep "artguard" || echo "")
if [ -n "$S3_BUCKETS" ]; then
    echo "$S3_BUCKETS"
    echo "✅ Buckets found"
else
    echo "❌ No buckets found"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2. ECS Cluster"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
CLUSTER=$(aws ecs list-clusters --region "$AWS_REGION" --query "clusterArns[?contains(@, 'artguard')]" --output text 2>/dev/null || echo "")
if [ -n "$CLUSTER" ]; then
    echo "✅ Cluster: $CLUSTER"
    aws ecs describe-clusters --clusters "$CLUSTER" --region "$AWS_REGION" --query "clusters[0].{Status:status,RunningTasks:runningTasksCount,ActiveServices:activeServicesCount}" --output table 2>/dev/null || echo "⚠️  Could not describe cluster"
    
    # Check services
    echo ""
    echo "ECS Services:"
    aws ecs list-services --cluster "$CLUSTER" --region "$AWS_REGION" --query "serviceArns" --output table 2>/dev/null || echo "⚠️  Could not list services"
else
    echo "❌ No cluster found"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3. DynamoDB Tables"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
DDB_TABLES=$(aws dynamodb list-tables --region "$AWS_REGION" --query "TableNames[?contains(@, 'artguard')]" --output table 2>/dev/null || echo "")
if [ -n "$DDB_TABLES" ]; then
    echo "$DDB_TABLES"
    echo "✅ Tables found"
else
    echo "❌ No tables found"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4. Lambda Functions"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
LAMBDA_FUNCTIONS=$(aws lambda list-functions --region "$AWS_REGION" --query "Functions[?contains(FunctionName, 'artguard')].FunctionName" --output table 2>/dev/null || echo "")
if [ -n "$LAMBDA_FUNCTIONS" ]; then
    echo "$LAMBDA_FUNCTIONS"
    echo "✅ Functions found"
else
    echo "❌ No functions found"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5. Application Load Balancer"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ALB_ARN=$(aws elbv2 describe-load-balancers --region "$AWS_REGION" --query "LoadBalancers[?contains(LoadBalancerName, 'artguard')].LoadBalancerArn" --output text 2>/dev/null || echo "")
if [ -n "$ALB_ARN" ]; then
    echo "✅ ALB found: $ALB_ARN"
    aws elbv2 describe-load-balancers --load-balancer-arns "$ALB_ARN" --region "$AWS_REGION" --query "LoadBalancers[0].{Name:LoadBalancerName,State:State.Code,DNSName:DNSName}" --output table 2>/dev/null || echo "⚠️  Could not describe ALB"
else
    echo "❌ No ALB found"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6. Application Health Checks"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -n "$BACKEND_URL" ]; then
    echo "Testing backend: $BACKEND_URL/health"
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BACKEND_URL/health" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo "✅ Backend is healthy (HTTP $HTTP_CODE)"
    else
        echo "❌ Backend not responding (HTTP $HTTP_CODE)"
    fi
else
    echo "⚠️  Backend URL not available"
fi

if [ -n "$FRONTEND_URL" ]; then
    echo ""
    echo "Testing frontend: $FRONTEND_URL"
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$FRONTEND_URL" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "403" ]; then
        echo "✅ Frontend is accessible (HTTP $HTTP_CODE)"
    else
        echo "❌ Frontend not responding (HTTP $HTTP_CODE)"
    fi
else
    echo "⚠️  Frontend URL not available"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Verification Complete"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"




