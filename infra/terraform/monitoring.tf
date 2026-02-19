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
            ["AWS/ECS", "CPUUtilization", { ServiceName = aws_ecs_service.backend.name, ClusterName = aws_ecs_cluster.main.name, stat = "Average", label = "CPU %" }],
            [".", "MemoryUtilization", { ServiceName = aws_ecs_service.backend.name, ClusterName = aws_ecs_cluster.main.name, stat = "Average", label = "Memory %" }]
          ]
          region = var.aws_region
          title  = "ECS - CPU & Memory"
          period = 300
        }
      },
      # ALB Request Count
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/ApplicationELB", "RequestCount", { LoadBalancer = aws_lb.backend.arn_suffix, stat = "Sum", label = "Requests" }],
            [".", "HTTPCode_Target_2XX_Count", { LoadBalancer = aws_lb.backend.arn_suffix, stat = "Sum", label = "2xx" }],
            [".", "HTTPCode_Target_4XX_Count", { LoadBalancer = aws_lb.backend.arn_suffix, stat = "Sum", label = "4xx" }],
            [".", "HTTPCode_Target_5XX_Count", { LoadBalancer = aws_lb.backend.arn_suffix, stat = "Sum", label = "5xx" }]
          ]
          region = var.aws_region
          title  = "ALB - Request Metrics"
          period = 300
        }
      },
      # DynamoDB Read/Write Capacity
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/DynamoDB", "ConsumedReadCapacityUnits", { TableName = aws_dynamodb_table.inference_records.name, stat = "Sum", label = "Inferences Read" }],
            [".", "ConsumedWriteCapacityUnits", { TableName = aws_dynamodb_table.inference_records.name, stat = "Sum", label = "Inferences Write" }],
            [".", "ConsumedReadCapacityUnits", { TableName = aws_dynamodb_table.users.name, stat = "Sum", label = "Users Read" }],
            [".", "ConsumedWriteCapacityUnits", { TableName = aws_dynamodb_table.users.name, stat = "Sum", label = "Users Write" }]
          ]
          region = var.aws_region
          title  = "DynamoDB - Consumed Capacity"
          period = 300
        }
      },
      # S3 Bucket Size 
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/S3", "BucketSizeBytes", { BucketName = aws_s3_bucket.images_raw.id, StorageType = "StandardStorage", stat = "Average" }],
            [".", ".", { BucketName = aws_s3_bucket.images_processed.id, StorageType = "StandardStorage", stat = "Average" }]
          ]
          region = var.aws_region
          title  = "S3 - Bucket Size"
          period = 86400 # Daily
        }
      }
    ]
  })
}
