# =============================================================================
# CloudWatch Monitoring — Dashboard, Alarms, and Log Metric Filters
# =============================================================================

# ---------------------------------------------------------------------------
# CloudWatch Dashboard
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${local.project_name}-dashboard"

  dashboard_body = jsonencode({
    widgets = [
      # --- Row 1: ECS Infrastructure ---
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/ECS", "CPUUtilization", "ClusterName", "${local.project_name}-cluster", "ServiceName", "${local.project_name}-service"],
            ["AWS/ECS", "MemoryUtilization", "ClusterName", "${local.project_name}-cluster", "ServiceName", "${local.project_name}-service"]
          ]
          stat   = "Average"
          period = 300
          region = var.aws_region
          title  = "ECS — CPU & Memory Utilization"
          yAxis  = { left = { min = 0, max = 100 } }
        }
      },
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/ECS", "RunningTaskCount", "ClusterName", "${local.project_name}-cluster", "ServiceName", "${local.project_name}-service"]
          ]
          stat   = "Average"
          period = 60
          region = var.aws_region
          title  = "ECS — Running Task Count"
        }
      },

      # --- Row 2: ALB Request & Error Metrics ---
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", aws_lb.backend.arn_suffix],
            ["AWS/ApplicationELB", "HTTPCode_Target_2XX_Count", "LoadBalancer", aws_lb.backend.arn_suffix]
          ]
          stat   = "Sum"
          period = 300
          region = var.aws_region
          title  = "ALB — Requests & 2XX Successes"
        }
      },
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/ApplicationELB", "HTTPCode_Target_4XX_Count", "LoadBalancer", aws_lb.backend.arn_suffix],
            ["AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "LoadBalancer", aws_lb.backend.arn_suffix]
          ]
          stat   = "Sum"
          period = 300
          region = var.aws_region
          title  = "ALB — 4XX & 5XX Error Rates"
          annotations = {
            horizontal = [
              { label = "Alert Threshold", value = 10 }
            ]
          }
        }
      },

      # --- Row 3: API Latency (Target Response Time) ---
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", aws_lb.backend.arn_suffix, { stat = "Average" }],
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", aws_lb.backend.arn_suffix, { stat = "p99" }]
          ]
          period = 300
          region = var.aws_region
          title  = "ALB — Target Response Time (avg & p99)"
          yAxis  = { left = { label = "Seconds" } }
        }
      },

      # --- Row 3b: Custom App Metrics (from EMF logs) ---
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["ArtGuard", "InferenceLatency", "Endpoint", "inference", { stat = "Average" }],
            ["ArtGuard", "RAGLatency", "Endpoint", "rag", { stat = "Average" }]
          ]
          period = 300
          region = var.aws_region
          title  = "App — Inference & RAG Latency"
          yAxis  = { left = { label = "Seconds" } }
        }
      },

      # --- Row 4: DynamoDB Consumed Capacity ---
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/DynamoDB", "ConsumedReadCapacityUnits", "TableName", aws_dynamodb_table.inference_records.name],
            ["AWS/DynamoDB", "ConsumedWriteCapacityUnits", "TableName", aws_dynamodb_table.inference_records.name]
          ]
          stat   = "Sum"
          period = 300
          region = var.aws_region
          title  = "DynamoDB — Inference Table Capacity"
        }
      },
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["ArtGuard", "InferenceSuccess", "Endpoint", "inference", { stat = "Sum" }],
            ["ArtGuard", "InferenceError", "Endpoint", "inference", { stat = "Sum" }],
            ["ArtGuard", "RAGError", "Endpoint", "rag", { stat = "Sum" }]
          ]
          period = 300
          region = var.aws_region
          title  = "App — Inference & RAG Success/Error Counts"
        }
      },

      # --- Row 5: Application Logs ---
      {
        type   = "log"
        width  = 24
        height = 6
        properties = {
          query   = "fields @timestamp, level, message, request_id, user_id\n| filter level = 'ERROR'\n| sort @timestamp desc\n| limit 50"
          region  = var.aws_region
          stacked = false
          view    = "table"
          title   = "Recent Application Errors"
          source  = [aws_cloudwatch_log_group.ecs.name]
        }
      },

      # --- Row 6: S3 Bucket Size ---
      {
        type   = "metric"
        width  = 24
        height = 6
        properties = {
          metrics = [
            ["AWS/S3", "BucketSizeBytes", "BucketName", aws_s3_bucket.images_raw.bucket, "StorageType", "StandardStorage"],
            ["AWS/S3", "BucketSizeBytes", "BucketName", aws_s3_bucket.images_processed.bucket, "StorageType", "StandardStorage"]
          ]
          stat   = "Average"
          period = 86400
          region = var.aws_region
          title  = "S3 — Bucket Sizes"
          yAxis  = { left = { label = "Bytes" } }
        }
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# CloudWatch Alarms
# ---------------------------------------------------------------------------

# Alarm: High 5XX error rate from ALB targets
resource "aws_cloudwatch_metric_alarm" "alb_5xx_errors" {
  alarm_name          = "${local.project_name}-alb-5xx-errors"
  alarm_description   = "ALB target 5XX error count exceeded threshold"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  statistic           = "Sum"
  period              = 300
  threshold           = 10
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = aws_lb.backend.arn_suffix
  }

  tags = { Project = local.project_name }
}

# Alarm: High API latency (p99 > 10s)
resource "aws_cloudwatch_metric_alarm" "alb_high_latency" {
  alarm_name          = "${local.project_name}-alb-high-latency"
  alarm_description   = "ALB target p99 response time exceeded 10 seconds"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "TargetResponseTime"
  namespace           = "AWS/ApplicationELB"
  extended_statistic  = "p99"
  period              = 300
  threshold           = 10
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = aws_lb.backend.arn_suffix
  }

  tags = { Project = local.project_name }
}

# Alarm: ECS task CPU > 85%
resource "aws_cloudwatch_metric_alarm" "ecs_high_cpu" {
  alarm_name          = "${local.project_name}-ecs-high-cpu"
  alarm_description   = "ECS service CPU utilization exceeded 85%"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  statistic           = "Average"
  period              = 300
  threshold           = 85
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = "${local.project_name}-cluster"
    ServiceName = "${local.project_name}-service"
  }

  tags = { Project = local.project_name }
}

# Alarm: ECS task Memory > 85%
resource "aws_cloudwatch_metric_alarm" "ecs_high_memory" {
  alarm_name          = "${local.project_name}-ecs-high-memory"
  alarm_description   = "ECS service memory utilization exceeded 85%"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "MemoryUtilization"
  namespace           = "AWS/ECS"
  statistic           = "Average"
  period              = 300
  threshold           = 85
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = "${local.project_name}-cluster"
    ServiceName = "${local.project_name}-service"
  }

  tags = { Project = local.project_name }
}

# Alarm: No healthy ECS tasks
resource "aws_cloudwatch_metric_alarm" "alb_no_healthy_hosts" {
  alarm_name          = "${local.project_name}-no-healthy-hosts"
  alarm_description   = "ALB target group has zero healthy hosts"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "HealthyHostCount"
  namespace           = "AWS/ApplicationELB"
  statistic           = "Minimum"
  period              = 60
  threshold           = 1
  treat_missing_data  = "breaching"

  dimensions = {
    LoadBalancer  = aws_lb.backend.arn_suffix
    TargetGroup   = aws_lb_target_group.backend.arn_suffix
  }

  tags = { Project = local.project_name }
}

# Alarm: DynamoDB throttling on any table
resource "aws_cloudwatch_metric_alarm" "dynamodb_throttle_inferences" {
  alarm_name          = "${local.project_name}-dynamodb-throttle-inferences"
  alarm_description   = "DynamoDB throttling detected on inference records table"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ThrottledRequests"
  namespace           = "AWS/DynamoDB"
  statistic           = "Sum"
  period              = 300
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    TableName = aws_dynamodb_table.inference_records.name
  }

  tags = { Project = local.project_name }
}

# ---------------------------------------------------------------------------
# Log Metric Filters — extract custom metrics from application logs
# ---------------------------------------------------------------------------

# Count of ERROR-level log lines
resource "aws_cloudwatch_log_metric_filter" "app_errors" {
  name           = "${local.project_name}-app-errors"
  log_group_name = aws_cloudwatch_log_group.ecs.name
  pattern        = "{ $.level = \"ERROR\" }"

  metric_transformation {
    name          = "ApplicationErrors"
    namespace     = "ArtGuard"
    value         = "1"
    default_value = "0"
  }
}

# Count of WARNING-level log lines
resource "aws_cloudwatch_log_metric_filter" "app_warnings" {
  name           = "${local.project_name}-app-warnings"
  log_group_name = aws_cloudwatch_log_group.ecs.name
  pattern        = "{ $.level = \"WARNING\" }"

  metric_transformation {
    name          = "ApplicationWarnings"
    namespace     = "ArtGuard"
    value         = "1"
    default_value = "0"
  }
}

# Count of auth failures (401 responses in access logs)
resource "aws_cloudwatch_log_metric_filter" "auth_failures" {
  name           = "${local.project_name}-auth-failures"
  log_group_name = aws_cloudwatch_log_group.ecs.name
  pattern        = "{ $.status = 401 }"

  metric_transformation {
    name          = "AuthFailures"
    namespace     = "ArtGuard"
    value         = "1"
    default_value = "0"
  }
}

# Alarm: Spike in application errors
resource "aws_cloudwatch_metric_alarm" "app_error_spike" {
  alarm_name          = "${local.project_name}-app-error-spike"
  alarm_description   = "Application ERROR log count exceeded threshold"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ApplicationErrors"
  namespace           = "ArtGuard"
  statistic           = "Sum"
  period              = 300
  threshold           = 20
  treat_missing_data  = "notBreaching"

  tags = { Project = local.project_name }
}
