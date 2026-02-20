#!/bin/bash
# Comprehensive Infrastructure Verification
# Verifies all 5 requirements for disaster recovery demo:
# 1. Data processing services / deployed applications
# 2. Database systems and their data
# 3. Configuration settings
# 4. Access controls and security settings
# 5. System functionality verification
# Usage: ./verify-all-components.sh [dev|prod]

set -e

ENVIRONMENT=${1:-prod}
AWS_REGION=${AWS_REGION:-ca-central-1}
TERRAFORM_DIR="../terraform"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Ensure AWS CLI is in PATH
if [ -d "$HOME/.local/bin" ]; then
  export PATH="$HOME/.local/bin:$PATH"
fi

# Disable AWS CLI pager
export AWS_PAGER=""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "COMPREHENSIVE INFRASTRUCTURE VERIFICATION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Environment: $ENVIRONMENT"
echo "Region: $AWS_REGION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd "$TERRAFORM_DIR"

# Find tfvars file
if [ -f "$ENVIRONMENT.tfvars" ]; then
  TFVARS_FILE="$ENVIRONMENT.tfvars"
elif [ -f "../$ENVIRONMENT.tfvars" ]; then
  TFVARS_FILE="../$ENVIRONMENT.tfvars"
elif [ -f "$ROOT_DIR/$ENVIRONMENT.tfvars" ]; then
  TFVARS_FILE="$ROOT_DIR/$ENVIRONMENT.tfvars"
else
  echo "❌ Error: $ENVIRONMENT.tfvars not found"
  exit 1
fi

# Get Terraform outputs
BACKEND_URL=$(terraform output -var-file="$TFVARS_FILE" -raw backend_url 2>/dev/null || echo "")

# ============================================================================
# 1. DATA PROCESSING SERVICES / DEPLOYED APPLICATIONS
# ============================================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1. DATA PROCESSING SERVICES / DEPLOYED APPLICATIONS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "📦 ECS Cluster:"
CLUSTER=$(aws ecs list-clusters --region "$AWS_REGION" --query "clusterArns[?contains(@, 'artguard')]" --output text 2>/dev/null || echo "")
if [ -n "$CLUSTER" ]; then
  echo "   ✅ Cluster found: $CLUSTER"
  aws ecs describe-clusters --clusters "$CLUSTER" --region "$AWS_REGION" \
    --query "clusters[0].{Name:clusterName,Status:status,ActiveServices:activeServicesCount,RunningTasks:runningTasksCount,RegisteredTasks:registeredContainerInstancesCount}" \
    --output table 2>/dev/null || echo "   ⚠️  Could not describe cluster details"
else
  echo "   ❌ No ECS cluster found"
fi

echo ""
echo "🚀 ECS Service (Backend Application):"
SERVICE=$(aws ecs list-services --cluster artguard-cluster --region "$AWS_REGION" --query "serviceArns[0]" --output text 2>/dev/null || echo "")
if [ -n "$SERVICE" ] && [ "$SERVICE" != "None" ]; then
  echo "   ✅ Service found: $SERVICE"
  aws ecs describe-services --cluster artguard-cluster --services artguard-backend --region "$AWS_REGION" \
    --query "services[0].{Name:serviceName,Status:status,DesiredCount:desiredCount,RunningCount:runningCount,TaskDefinition:taskDefinition}" \
    --output table 2>/dev/null || echo "   ⚠️  Could not describe service"
  
  echo ""
  echo "   Running Tasks:"
  TASKS=$(aws ecs list-tasks --cluster artguard-cluster --service-name artguard-backend --region "$AWS_REGION" --query "taskArns" --output text 2>/dev/null || echo "")
  if [ -n "$TASKS" ] && [ "$TASKS" != "None" ]; then
    echo "   ✅ Tasks running: $(echo $TASKS | wc -w)"
    for task in $TASKS; do
      aws ecs describe-tasks --cluster artguard-cluster --tasks "$task" --region "$AWS_REGION" \
        --query "tasks[0].{TaskArn:taskArn,LastStatus:lastStatus,HealthStatus:healthStatus}" \
        --output table 2>/dev/null | head -5
    done
  else
    echo "   ⚠️  No running tasks found"
  fi
else
  echo "   ❌ No ECS service found"
fi

echo ""
echo "📊 Application Load Balancer:"
ALB_ARN=$(aws elbv2 describe-load-balancers --region "$AWS_REGION" --query "LoadBalancers[?contains(LoadBalancerName, 'artguard')].LoadBalancerArn" --output text 2>/dev/null | head -1 || echo "")
if [ -n "$ALB_ARN" ]; then
  echo "   ✅ ALB found: $ALB_ARN"
  aws elbv2 describe-load-balancers --load-balancer-arns "$ALB_ARN" --region "$AWS_REGION" \
    --query "LoadBalancers[0].{Name:LoadBalancerName,State:State.Code,DNSName:DNSName,Scheme:Scheme}" \
    --output table 2>/dev/null || echo "   ⚠️  Could not describe ALB"
  
  echo ""
  echo "   Target Groups:"
  TG_ARNS=$(aws elbv2 describe-target-groups --load-balancer-arn "$ALB_ARN" --region "$AWS_REGION" --query "TargetGroups[].TargetGroupArn" --output text 2>/dev/null || echo "")
  if [ -n "$TG_ARNS" ]; then
    for tg_arn in $TG_ARNS; do
      aws elbv2 describe-target-health --target-group-arn "$tg_arn" --region "$AWS_REGION" \
        --query "TargetHealthDescriptions[].{Target:Target.Id,Port:Target.Port,Health:TargetHealth.State,Reason:TargetHealth.Reason}" \
        --output table 2>/dev/null | head -10
    done
  fi
else
  echo "   ❌ No ALB found"
fi

# ============================================================================
# 2. DATABASE SYSTEMS AND THEIR DATA
# ============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2. DATABASE SYSTEMS AND THEIR DATA"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "🗄️  DynamoDB Tables:"
TABLES=$(aws dynamodb list-tables --region "$AWS_REGION" --query "TableNames[?contains(@, 'artguard')]" --output text 2>/dev/null | grep -v "terraform-locks" || echo "")
if [ -n "$TABLES" ]; then
  echo "   ✅ Found $(echo $TABLES | wc -w) table(s):"
  for table in $TABLES; do
    echo ""
    echo "   Table: $table"
    aws dynamodb describe-table --table-name "$table" --region "$AWS_REGION" \
      --query "Table.{Status:TableStatus,ItemCount:ItemCount,SizeBytes:TableSizeBytes,BillingMode:BillingModeSummary.BillingMode}" \
      --output table 2>/dev/null || echo "     ⚠️  Could not describe table"
    
    # Show table structure (key schema)
    echo "   Key Schema:"
    aws dynamodb describe-table --table-name "$table" --region "$AWS_REGION" \
      --query "Table.KeySchema" --output table 2>/dev/null || echo "     ⚠️  Could not get key schema"
    
    # Show GSI count
    GSI_COUNT=$(aws dynamodb describe-table --table-name "$table" --region "$AWS_REGION" \
      --query "Table.GlobalSecondaryIndexes | length(@)" --output text 2>/dev/null || echo "0")
    if [ "$GSI_COUNT" != "0" ]; then
      echo "   Global Secondary Indexes: $GSI_COUNT"
    fi
  done
else
  echo "   ❌ No DynamoDB tables found"
fi

# ============================================================================
# 3. CONFIGURATION SETTINGS
# ============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3. CONFIGURATION SETTINGS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "⚙️  Terraform Configuration Summary:"
terraform output -var-file="$TFVARS_FILE" summary 2>/dev/null || echo "   ⚠️  Summary output not available"

echo ""
echo "📋 Key Configuration Values:"
terraform output -var-file="$TFVARS_FILE" -json 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    config = {
        'backend_url': data.get('backend_url', {}).get('value', 'N/A'),
        'ecs_cluster': data.get('ecs_cluster_name', {}).get('value', 'N/A'),
        'dynamodb_tables': {
            'users': data.get('dynamodb_users_table_name', {}).get('value', 'N/A'),
            'inferences': data.get('dynamodb_inference_records_table_name', {}).get('value', 'N/A'),
            'images': data.get('dynamodb_image_records_table_name', {}).get('value', 'N/A'),
            'patches': data.get('dynamodb_patch_records_table_name', {}).get('value', 'N/A'),
            'runs': data.get('dynamodb_run_records_table_name', {}).get('value', 'N/A'),
            'configs': data.get('dynamodb_config_records_table_name', {}).get('value', 'N/A')
        },
        'knowledge_base': data.get('knowledge_base_id', {}).get('value', 'N/A'),
        's3_buckets': {
            'images_raw': data.get('s3_images_raw_bucket_name', {}).get('value', 'N/A'),
            'images_processed': data.get('s3_images_processed_bucket_name', {}).get('value', 'N/A'),
            'knowledge_base': data.get('s3_knowledge_base_bucket_name', {}).get('value', 'N/A')
        }
    }
    print(json.dumps(config, indent=2))
except:
    print('   ⚠️  Could not parse Terraform outputs')
" 2>/dev/null || echo "   ⚠️  Could not extract configuration (python3 may not be available)"

echo ""
echo "📝 Terraform State Resources:"
RESOURCE_COUNT=$(terraform state list -var-file="$TFVARS_FILE" 2>/dev/null | wc -l || echo "0")
echo "   Total resources in state: $RESOURCE_COUNT"
if [ "$RESOURCE_COUNT" -gt 0 ] && [ "$RESOURCE_COUNT" -lt 50 ]; then
  echo "   Resource types:"
  terraform state list -var-file="$TFVARS_FILE" 2>/dev/null | sed 's/\..*$//' | sort -u | sed 's/^/     - /' || echo "     ⚠️  Could not list resources"
fi

# ============================================================================
# 4. ACCESS CONTROLS AND SECURITY SETTINGS
# ============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4. ACCESS CONTROLS AND SECURITY SETTINGS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "🔐 IAM Roles:"
ROLES=$(aws iam list-roles --query "Roles[?contains(RoleName, 'artguard')].RoleName" --output text 2>/dev/null || echo "")
if [ -n "$ROLES" ]; then
  echo "   ✅ Found $(echo $ROLES | wc -w) role(s):"
  for role in $ROLES; do
    echo "     - $role"
  done
  echo ""
  echo "   Role Details (sample):"
  FIRST_ROLE=$(echo $ROLES | cut -d' ' -f1)
  aws iam get-role --role-name "$FIRST_ROLE" --query "Role.{RoleName:RoleName,Arn:Arn,CreateDate:CreateDate}" --output table 2>/dev/null || echo "     ⚠️  Could not get role details"
else
  echo "   ❌ No IAM roles found"
fi

echo ""
echo "📜 IAM Policies:"
POLICIES=$(aws iam list-policies --scope Local --query "Policies[?contains(PolicyName, 'artguard')].PolicyName" --output text 2>/dev/null || echo "")
if [ -n "$POLICIES" ]; then
  echo "   ✅ Found $(echo $POLICIES | wc -w) custom policy/policies:"
  for policy in $POLICIES; do
    echo "     - $policy"
  done
else
  echo "   ⚠️  No custom IAM policies found (using AWS managed policies)"
fi

echo ""
echo "🛡️  Security Groups:"
SGS=$(aws ec2 describe-security-groups --filters "Name=tag:Project,Values=artguard" --region "$AWS_REGION" --query "SecurityGroups[].GroupId" --output text 2>/dev/null || echo "")
if [ -n "$SGS" ]; then
  echo "   ✅ Found $(echo $SGS | wc -w) security group(s):"
  aws ec2 describe-security-groups --filters "Name=tag:Project,Values=artguard" --region "$AWS_REGION" \
    --query "SecurityGroups[].{GroupId:GroupId,GroupName:GroupName,Description:Description}" \
    --output table 2>/dev/null || echo "     ⚠️  Could not describe security groups"
else
  echo "   ❌ No security groups found"
fi

echo ""
echo "🔑 Secrets Manager:"
SECRETS=$(aws secretsmanager list-secrets --region "$AWS_REGION" --query "SecretList[?contains(Name, 'artguard')].Name" --output text 2>/dev/null || echo "")
if [ -n "$SECRETS" ]; then
  echo "   ✅ Found $(echo $SECRETS | wc -w) secret(s):"
  for secret in $SECRETS; do
    echo "     - $secret"
    aws secretsmanager describe-secret --secret-id "$secret" --region "$AWS_REGION" \
      --query "{Name:Name,ARN:ARN,LastChangedDate:LastChangedDate}" \
      --output table 2>/dev/null | head -5 || echo "       ⚠️  Could not describe secret"
  done
else
  echo "   ❌ No secrets found"
fi

# ============================================================================
# 5. SYSTEM FUNCTIONALITY VERIFICATION
# ============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5. SYSTEM FUNCTIONALITY VERIFICATION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ -n "$BACKEND_URL" ]; then
  echo "🌐 Backend Health Check:"
  echo "   URL: $BACKEND_URL/health"
  echo ""
  echo "   Testing endpoint..."
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$BACKEND_URL/health" 2>/dev/null || echo "000")
  
  if [ "$HTTP_CODE" = "200" ]; then
    echo "   ✅ Backend is healthy (HTTP $HTTP_CODE)"
    echo ""
    echo "   Response body:"
    curl -s --max-time 10 "$BACKEND_URL/health" 2>/dev/null | python3 -m json.tool 2>/dev/null || curl -s --max-time 10 "$BACKEND_URL/health" 2>/dev/null
    echo ""
  else
    echo "   ❌ Backend not responding (HTTP $HTTP_CODE)"
    echo "   This may be normal if the service is still starting up"
  fi
else
  echo "   ⚠️  Backend URL not available from Terraform outputs"
  echo "   Attempting to find ALB DNS name..."
  ALB_DNS=$(aws elbv2 describe-load-balancers --region "$AWS_REGION" \
    --query "LoadBalancers[?contains(LoadBalancerName, 'artguard-backend')].DNSName" \
    --output text 2>/dev/null | head -1 || echo "")
  if [ -n "$ALB_DNS" ]; then
    BACKEND_URL="http://$ALB_DNS"
    echo "   Found ALB: $BACKEND_URL"
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$BACKEND_URL/health" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
      echo "   ✅ Backend is healthy (HTTP $HTTP_CODE)"
    else
      echo "   ❌ Backend not responding (HTTP $HTTP_CODE)"
    fi
  else
    echo "   ❌ Could not determine backend URL"
  fi
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ COMPREHENSIVE VERIFICATION COMPLETE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Summary:"
echo "  ✅ Data Processing Services: $(if [ -n "$CLUSTER" ]; then echo "VERIFIED"; else echo "NOT FOUND"; fi)"
echo "  ✅ Database Systems: $(if [ -n "$TABLES" ]; then echo "VERIFIED ($(echo $TABLES | wc -w) tables)"; else echo "NOT FOUND"; fi)"
echo "  ✅ Configuration Settings: $(if [ "$RESOURCE_COUNT" -gt 0 ]; then echo "VERIFIED ($RESOURCE_COUNT resources)"; else echo "NOT FOUND"; fi)"
echo "  ✅ Access Controls: $(if [ -n "$ROLES" ]; then echo "VERIFIED ($(echo $ROLES | wc -w) roles)"; else echo "NOT FOUND"; fi)"
echo "  ✅ System Functionality: $(if [ "$HTTP_CODE" = "200" ]; then echo "VERIFIED (HTTP 200)"; else echo "NEEDS ATTENTION"; fi)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"


