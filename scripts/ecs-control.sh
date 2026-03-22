#!/bin/bash
set -e

# ECS Service Control Script
# Manage ArtGuard's ECS backend service: deploy, scale, check status, or tail logs.
#
# Usage: ./ecs-control.sh [action] [environment] [desired_count]
# Actions: deploy, scale, status, logs
# Examples:
#   ./ecs-control.sh deploy dev        # Force new deployment with latest image
#   ./ecs-control.sh scale dev 2       # Scale to 2 tasks
#   ./ecs-control.sh scale dev 0       # Pause service (no compute cost)
#   ./ecs-control.sh status dev        # Check health and task counts
#   ./ecs-control.sh logs dev          # Tail recent CloudWatch logs

source "$(dirname "$0")/_colors.sh"

export AWS_PAGER=""

ACTION=${1:-status}
ENVIRONMENT=${2:-dev}
DESIRED_COUNT=${3:-1}
AWS_REGION=${AWS_REGION:-ca-central-1}
ECS_CLUSTER=${ECS_CLUSTER:-artguard-cluster}
ECS_SERVICE=${ECS_SERVICE:-artguard-backend}

case $ACTION in
  deploy)
    step "Forcing new ECS deployment..."
    aws ecs update-service \
      --cluster $ECS_CLUSTER \
      --service $ECS_SERVICE \
      --force-new-deployment \
      --region $AWS_REGION

    success "Deployment initiated!"
    info "New tasks will start in ~2-3 minutes."
    ;;

  scale)
    step "Scaling ECS service to $DESIRED_COUNT tasks..."
    aws ecs update-service \
      --cluster $ECS_CLUSTER \
      --service $ECS_SERVICE \
      --desired-count $DESIRED_COUNT \
      --region $AWS_REGION

    success "Scale operation initiated!"
    if [ "$DESIRED_COUNT" -eq "0" ]; then
      warn "Service scaled to 0 (paused). No compute costs while paused."
      warn "ALB health checks will fail until scaled back up."
    else
      success "Service scaling to $DESIRED_COUNT task(s)."
    fi
    ;;

  status)
    step "Checking ECS service status..."
    echo ""

    # Fetch all service metrics in a single API call and extract with JMESPath
    SERVICE_JSON=$(aws ecs describe-services \
      --cluster $ECS_CLUSTER \
      --services $ECS_SERVICE \
      --region $AWS_REGION \
      --output json)

    DESIRED=$(echo "$SERVICE_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['services'][0]['desiredCount'])")
    RUNNING=$(echo "$SERVICE_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['services'][0]['runningCount'])")
    PENDING=$(echo "$SERVICE_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['services'][0]['pendingCount'])")
    STATUS=$(echo "$SERVICE_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['services'][0]['status'])")
    DEPLOYMENTS=$(echo "$SERVICE_JSON" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['services'][0]['deployments']))")

    header "ECS Service Status"
    echo -e "  Cluster: ${CYAN}$ECS_CLUSTER${NC}"
    echo -e "  Service: ${CYAN}$ECS_SERVICE${NC}"
    echo -e "  Status:  ${BOLD}$STATUS${NC}"
    echo ""
    echo -e "  Tasks:"
    echo -e "    Desired: ${CYAN}$DESIRED${NC}"
    echo -e "    Running: ${GREEN}$RUNNING${NC}"
    echo -e "    Pending: ${YELLOW}$PENDING${NC}"
    echo ""
    echo -e "  Active Deployments: ${CYAN}$DEPLOYMENTS${NC}"

    if [ "$DEPLOYMENTS" -gt "1" ]; then
      warn "Multiple deployments active (rolling update in progress)."
    fi

    if [ "$RUNNING" -eq "$DESIRED" ] && [ "$PENDING" -eq "0" ]; then
      success "Service is healthy and stable."
    elif [ "$DESIRED" -eq "0" ]; then
      warn "Service is scaled to 0 (paused)."
    else
      info "Service is transitioning to desired state..."
    fi

    echo ""
    info "Recent Events (last 5):"
    # Parse events JSON with Python for reliable formatting
    echo "$SERVICE_JSON" | python3 -c "
import sys, json
svc = json.load(sys.stdin)['services'][0]
for ev in svc.get('events', [])[:5]:
    ts = ev['createdAt'][:19].replace('T', ' ')
    print(f'  [{ts}] {ev[\"message\"]}')
"
    ;;

  logs)
    step "Fetching recent ECS task logs..."
    echo ""

    # Find the most recent running task
    TASK_ARN=$(aws ecs list-tasks \
      --cluster $ECS_CLUSTER \
      --service-name $ECS_SERVICE \
      --desired-status RUNNING \
      --region $AWS_REGION \
      --query 'taskArns[0]' \
      --output text)

    if [ -z "$TASK_ARN" ] || [ "$TASK_ARN" == "None" ]; then
      error "No running tasks found."
      echo -e "  ${DIM}Service may be scaled to 0 or tasks may be starting.${NC}"
      exit 0
    fi

    info "Task: $(basename $TASK_ARN)"
    echo ""
    header "Recent logs (last 50 lines)"

    aws logs tail /ecs/artguard-backend \
      --since 10m \
      --format short \
      --region $AWS_REGION \
      | tail -n 50

    echo ""
    echo -e "To stream live logs:"
    echo -e "  ${GREEN}aws logs tail /ecs/artguard-backend --follow --region $AWS_REGION${NC}"
    ;;

  *)
    error "Invalid action: $ACTION"
    echo ""
    echo -e "Usage: ${CYAN}./ecs-control.sh [action] [environment] [desired_count]${NC}"
    echo ""
    echo "Actions:"
    echo -e "  ${GREEN}deploy${NC}  - Force new deployment with latest image"
    echo -e "  ${GREEN}scale${NC}   - Change desired task count"
    echo -e "  ${GREEN}status${NC}  - Check service health and task counts"
    echo -e "  ${GREEN}logs${NC}    - Fetch recent CloudWatch logs"
    echo ""
    echo "Examples:"
    echo -e "  ${DIM}./ecs-control.sh deploy dev${NC}"
    echo -e "  ${DIM}./ecs-control.sh scale dev 2${NC}"
    echo -e "  ${DIM}./ecs-control.sh scale dev 0  # Pause service${NC}"
    echo -e "  ${DIM}./ecs-control.sh status dev${NC}"
    echo -e "  ${DIM}./ecs-control.sh logs dev${NC}"
    exit 1
    ;;
esac
