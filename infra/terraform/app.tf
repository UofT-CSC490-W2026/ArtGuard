# ECR Repository - Docker image storage for FastAPI backend

resource "aws_ecr_repository" "backend" {
  name                 = "${local.project_name}-backend"
  image_tag_mutability = "MUTABLE"
  force_delete         = var.environment != "prod" # Allow deletion with images in non-prod environments

  image_scanning_configuration {
    scan_on_push = var.ecr_scan_on_push
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Name    = "${local.project_name}-backend-ecr"
    Purpose = "Backend Docker Image Repository"
  }
}

# ECR Lifecycle Policy - Automatically clean up old images
resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last ${var.ecr_image_retention_count} images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["v"]
          countType     = "imageCountMoreThan"
          countNumber   = var.ecr_image_retention_count
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Delete untagged images after ${var.ecr_untagged_image_days} days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = var.ecr_untagged_image_days
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}


# Application Load Balancer
resource "aws_lb" "backend" {
  name               = "${local.project_name}-backend-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  enable_deletion_protection       = var.environment == "prod" ? true : false
  enable_http2                     = true
  enable_cross_zone_load_balancing = true

  tags = {
    Name = "${local.project_name}-backend-alb"
  }
}

# ALB Target Group
resource "aws_lb_target_group" "backend" {
  name        = "${local.project_name}-backend-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    enabled             = true
    path                = "/health"
    port                = "traffic-port"
    protocol            = "HTTP"
    healthy_threshold   = var.ecs_health_check_healthy_threshold
    unhealthy_threshold = var.ecs_health_check_unhealthy_threshold
    timeout             = var.ecs_health_check_timeout
    interval            = var.ecs_health_check_interval
    matcher             = "200"
  }

  deregistration_delay = 30

  tags = {
    Name = "${local.project_name}-backend-tg"
  }
}

# ALB Listener (HTTP)
resource "aws_lb_listener" "backend_http" {
  load_balancer_arn = aws_lb.backend.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
}

# ALB Listener (HTTPS) - Optional, requires ACM certificate
resource "aws_lb_listener" "backend_https" {
  count             = var.enable_custom_domain ? 1 : 0
  load_balancer_arn = aws_lb.backend.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.enable_custom_domain ? aws_acm_certificate.backend[0].arn : null

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  depends_on = [aws_acm_certificate_validation.backend]
}

# ACM Certificate for ALB (if custom domain enabled)
resource "aws_acm_certificate" "backend" {
  count             = var.enable_custom_domain ? 1 : 0
  domain_name       = "api.${var.domain_name}"
  validation_method = "DNS"

  tags = {
    Name = "${local.project_name}-backend-cert"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# ACM Certificate Validation
resource "aws_acm_certificate_validation" "backend" {
  count                   = var.enable_custom_domain ? 1 : 0
  certificate_arn         = aws_acm_certificate.backend[0].arn
  validation_record_fqdns = [for record in aws_route53_record.backend_cert_validation : record.fqdn]
}

# Route53 Record for Certificate Validation
resource "aws_route53_record" "backend_cert_validation" {
  for_each = var.enable_custom_domain ? {
    for dvo in aws_acm_certificate.backend[0].domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  } : {}

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = aws_route53_zone.main[0].zone_id
}


# ECS Fargate Cluster
resource "aws_ecs_cluster" "main" {
  name = "${local.project_name}-cluster"

  setting {
    name  = "containerInsights"
    value = var.enable_container_insights ? "enabled" : "disabled"
  }

  tags = {
    Name = "${local.project_name}-ecs-cluster"
  }
}

# ECS Cluster Capacity Providers
resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = var.use_fargate_spot ? "FARGATE_SPOT" : "FARGATE"
    weight            = 100
    base              = 1
  }
}

# CloudWatch Log Group for ECS
resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/${local.project_name}-backend"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${local.project_name}-ecs-logs"
  }
}

# ECS Task Definition 
# Defines the Docker container, resource requirements, environment variables, secrets, and logging for the FastAPI backend service
resource "aws_ecs_task_definition" "backend" {
  family                   = "${local.project_name}-backend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.ecs_cpu
  memory                   = var.ecs_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "backend"
      image     = "${aws_ecr_repository.backend.repository_url}:latest"
      essential = true

      portMappings = [
        {
          containerPort = 8000
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "ENVIRONMENT"
          value = var.environment
        },
        {
          name  = "AWS_REGION"
          value = var.aws_region
        },
        # S3 Buckets
        {
          name  = "S3_IMAGES_RAW_BUCKET"
          value = aws_s3_bucket.images_raw.id
        },
        {
          name  = "S3_IMAGES_PROCESSED_BUCKET"
          value = aws_s3_bucket.images_processed.id
        },
        {
          name  = "S3_KNOWLEDGE_BASE_BUCKET"
          value = aws_s3_bucket.knowledge_base.id
        },
        # DynamoDB Tables
        {
          name  = "DDB_USERS_TABLE"
          value = aws_dynamodb_table.users.name
        },
        {
          name  = "DDB_INFERENCES_TABLE"
          value = aws_dynamodb_table.inference_records.name
        },
        {
          name  = "DDB_IMAGES_TABLE"
          value = aws_dynamodb_table.image_records.name
        },
        {
          name  = "DDB_PATCHES_TABLE"
          value = aws_dynamodb_table.patch_records.name
        },
        {
          name  = "DDB_RUNS_TABLE"
          value = aws_dynamodb_table.run_records.name
        },
        {
          name  = "DDB_CONFIGS_TABLE"
          value = aws_dynamodb_table.config_records.name
        },
        # Legacy (for backward compatibility)
        {
          name  = "DYNAMODB_TABLE_NAME"
          value = aws_dynamodb_table.image_records.name
        },
        # Bedrock
        {
          name  = "KNOWLEDGE_BASE_ID"
          value = aws_bedrockagent_knowledge_base.main.id
        },
        # Monitoring
        {
          name  = "AWS_XRAY_TRACING_ENABLED"
          value = var.enable_xray_tracing ? "true" : "false"
        }
      ]

      secrets = [
        {
          name      = "MODAL_API_KEY"
          valueFrom = aws_secretsmanager_secret.modal_api_key.arn
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = {
    Name = "${local.project_name}-backend-task"
  }
}

# ECS Service
# Manages the deployment and scaling of the ECS tasks
resource "aws_ecs_service" "backend" {
  name            = "${local.project_name}-backend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.ecs_desired_count
  launch_type     = var.use_fargate_spot ? null : "FARGATE"

  # Use capacity provider if Fargate Spot is enabled
  dynamic "capacity_provider_strategy" {
    for_each = var.use_fargate_spot ? [1] : []
    content {
      capacity_provider = "FARGATE_SPOT"
      weight            = 100
      base              = 1
    }
  }

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = 8000
  }

  # Enable ECS Exec for debugging
  enable_execute_command = var.environment == "dev" ? true : false

  # Deployment configuration
  deployment_maximum_percent         = 200
  deployment_minimum_healthy_percent = 100

  # Health check grace period
  health_check_grace_period_seconds = 60

  # Enable deployment circuit breaker
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  tags = {
    Name = "${local.project_name}-backend-service"
  }

  depends_on = [
    aws_lb_listener.backend_http,
    aws_iam_role_policy_attachment.ecs_execution_policy,
    aws_iam_role_policy_attachment.ecs_task_policy
  ]
}

# ECS Auto Scaling Target
resource "aws_appautoscaling_target" "ecs" {
  max_capacity       = var.ecs_max_capacity
  min_capacity       = var.ecs_min_capacity
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.backend.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

# ECS Auto Scaling Policy - CPU reaches capacity threshold
resource "aws_appautoscaling_policy" "ecs_cpu" {
  name               = "${local.project_name}-ecs-cpu-autoscaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.ecs.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = var.ecs_cpu_target
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# ECS Auto Scaling Policy - Memory reaches capacity threshold
resource "aws_appautoscaling_policy" "ecs_memory" {
  name               = "${local.project_name}-ecs-memory-autoscaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.ecs.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageMemoryUtilization"
    }
    target_value       = var.ecs_memory_target
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# ECS Auto Scaling Policy - Requests per target on ALB reaches threshold
resource "aws_appautoscaling_policy" "ecs_requests" {
  name               = "${local.project_name}-ecs-requests-autoscaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.ecs.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ALBRequestCountPerTarget"
      resource_label         = "${aws_lb.backend.arn_suffix}/${aws_lb_target_group.backend.arn_suffix}"
    }
    target_value       = var.ecs_request_count_target
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}
