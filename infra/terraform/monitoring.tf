# CloudWatch Dashboard

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${local.project_name}-dashboard"

  dashboard_body = jsonencode({
    widgets = [
      # ECS CPU and Memory
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/ECS", "CPUUtilization"],
            ["AWS/ECS", "MemoryUtilization"]
          ]
          stat   = "Average"
          period = 300
          region = var.aws_region
          title  = "ECS - CPU & Memory"
        }
      },
      # ALB Request Count
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/ApplicationELB", "RequestCount"],
            ["AWS/ApplicationELB", "HTTPCode_Target_2XX_Count"]
          ]
          stat   = "Sum"
          period = 300
          region = var.aws_region
          title  = "ALB - Request & Success Metrics"
        }
      },
      # ALB Error Count
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/ApplicationELB", "HTTPCode_Target_4XX_Count"],
            ["AWS/ApplicationELB", "HTTPCode_Target_5XX_Count"]
          ]
          stat   = "Sum"
          period = 300
          region = var.aws_region
          title  = "ALB - Error Metrics"
        }
      },
      # DynamoDB Consumed Capacity (all tables)
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/DynamoDB", "ConsumedReadCapacityUnits"],
            ["AWS/DynamoDB", "ConsumedWriteCapacityUnits"]
          ]
          stat   = "Sum"
          period = 300
          region = var.aws_region
          title  = "DynamoDB - Consumed Capacity"
        }
      },
      # S3 Bucket Size 
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/S3", "BucketSizeBytes"],
            ["AWS/S3", "BucketSizeBytes"]
          ]
          stat   = "Average"
          period = 86400 # Daily
          region = var.aws_region
          title  = "S3 - Bucket Size"
        }
      }
    ]
  })
}
