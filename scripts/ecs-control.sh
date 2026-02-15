#!/bin/bash
set -e

# ECS Service Control Script
# Usage: ./ecs-control.sh [action] [environment] [desired_count]
# Actions: deploy, scale, status, logs
# Examples:
#   ./ecs-control.sh deploy dev
#   ./ecs-control.sh scale dev 2
#   ./ecs-control.sh status dev
#   ./ecs-control.sh logs dev

ACTION=${1:-status}
ENVIRONMENT=${2:-dev}
DESIRED_COUNT=${3:-1}
AWS_REGION=${AWS_REGION:-ca-central-1}
ECS_CLUSTER=${ECS_CLUSTER:-artguard-cluster}
ECS_SERVICE=${ECS_SERVICE:-artguard-backend}

case $ACTION in
  deploy)
    echo "Forcing new ECS deployment..."
    aws ecs update-service \
      --cluster $ECS_CLUSTER \
      --service $ECS_SERVICE \
      --force-new-deployment \
      --region $AWS_REGION \
      --no-cli-pager

    echo "✅ Deployment initiated successfully!"
    echo "New tasks will start in ~2-3 minutes"
    ;;

  scale)
    echo "Scaling ECS service to $DESIRED_COUNT tasks..."
    aws ecs update-service \
      --cluster $ECS_CLUSTER \
      --service $ECS_SERVICE \
      --desired-count $DESIRED_COUNT \
      --region $AWS_REGION \
      --no-cli-pager

    echo "✅ Scale operation initiated!"
    if [ "$DESIRED_COUNT" -eq "0" ]; then
      echo "⚠️  Service scaled to 0 (paused)"
      echo "No compute costs while scaled to 0"
      echo "⚠️  ALB health checks will fail until scaled up"
    else
      echo "✅ Service scaling to $DESIRED_COUNT task(s)"
    fi
    ;;

  status)
    echo "Checking ECS service status..."
    echo ""

    SERVICE_JSON=$(aws ecs describe-services \
      --cluster $ECS_CLUSTER \
      --services $ECS_SERVICE \
      --region $AWS_REGION \
      --no-cli-pager)

    DESIRED=$(echo $SERVICE_JSON | jq -r '.services[0].desiredCount')
    RUNNING=$(echo $SERVICE_JSON | jq -r '.services[0].runningCount')
    PENDING=$(echo $SERVICE_JSON | jq -r '.services[0].pendingCount')
    STATUS=$(echo $SERVICE_JSON | jq -r '.services[0].status')
    DEPLOYMENTS=$(echo $SERVICE_JSON | jq -r '.services[0].deployments | length')

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "ECS Service Status"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Cluster: $ECS_CLUSTER"
    echo "Service: $ECS_SERVICE"
    echo "Status: $STATUS"
    echo ""
    echo "Tasks:"
    echo "  Desired: $DESIRED"
    echo "  Running: $RUNNING"
    echo "  Pending: $PENDING"
    echo ""
    echo "Active Deployments: $DEPLOYMENTS"

    if [ "$DEPLOYMENTS" -gt "1" ]; then
      echo "⚠️  Multiple deployments active (rolling update in progress)"
    fi

    if [ "$RUNNING" -eq "$DESIRED" ] && [ "$PENDING" -eq "0" ]; then
      echo "✅ Service is healthy and stable"
    elif [ "$DESIRED" -eq "0" ]; then
      echo "⏸Service is scaled to 0 (paused)"
    else
      echo "Service is transitioning to desired state"
    fi
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    echo ""
    echo "Recent Events (last 5):"
    echo $SERVICE_JSON | jq -r '.services[0].events[:5][] | "[\(.createdAt)] \(.message)"'
    ;;

  logs)
    echo "Fetching recent ECS task logs..."
    echo ""

    TASK_ARN=$(aws ecs list-tasks \
      --cluster $ECS_CLUSTER \
      --service-name $ECS_SERVICE \
      --desired-status RUNNING \
      --region $AWS_REGION \
      --query 'taskArns[0]' \
      --output text)

    if [ -z "$TASK_ARN" ] || [ "$TASK_ARN" == "None" ]; then
      echo "❌ No running tasks found"
      echo "   Service may be scaled to 0 or tasks may be starting"
      exit 0
    fi

    echo "Task: $(basename $TASK_ARN)"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Recent logs from CloudWatch (last 50 lines):"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    aws logs tail /ecs/artguard-backend \
      --since 10m \
      --format short \
      --region $AWS_REGION \
      | tail -n 50

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "To stream live logs, use:"
    echo "   aws logs tail /ecs/artguard-backend --follow --region $AWS_REGION"
    ;;

  *)
    echo "❌ Invalid action: $ACTION"
    echo ""
    echo "Usage: ./ecs-control.sh [action] [environment] [desired_count]"
    echo ""
    echo "Actions:"
    echo "  deploy  - Force new deployment with latest image"
    echo "  scale   - Change desired task count"
    echo "  status  - Check service health and task counts"
    echo "  logs    - Fetch recent CloudWatch logs"
    echo ""
    echo "Examples:"
    echo "  ./ecs-control.sh deploy dev"
    echo "  ./ecs-control.sh scale dev 2"
    echo "  ./ecs-control.sh scale dev 0  # Pause service"
    echo "  ./ecs-control.sh status dev"
    echo "  ./ecs-control.sh logs dev"
    exit 1
    ;;
esac
