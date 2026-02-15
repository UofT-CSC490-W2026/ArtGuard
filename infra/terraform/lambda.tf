# Lambda Function - Image Processing (Rotation, Blurring)
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/image_processor"
  output_path = "${path.module}/lambda_function.zip"
}

resource "aws_lambda_function" "image_processor" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "${local.project_name}-image-processor"
  role             = aws_iam_role.lambda_execution.arn
  handler          = "lambda_function.handler"
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  runtime          = var.lambda_runtime
  timeout          = var.lambda_timeout
  memory_size      = var.lambda_memory

  environment {
    variables = {
      PROCESSED_BUCKET = aws_s3_bucket.images_processed.id
      RAW_BUCKET       = aws_s3_bucket.images_raw.id
    }
  }

  # X-Ray distributed tracing
  tracing_config {
    mode = var.enable_xray_tracing ? "Active" : "PassThrough"
  }

  tags = {
    Name    = "${local.project_name}-image-processor"
    Purpose = "Image Processing Lambda"
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_execution_policy,
    aws_cloudwatch_log_group.lambda
  ]
}

# Lambda Permission - Allow S3 to invoke the Lambda function when new image added
resource "aws_lambda_permission" "allow_s3_invoke" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.image_processor.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.images_raw.arn
}

# CloudWatch Log Group for Lambda
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.project_name}-image-processor"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${local.project_name}-lambda-logs"
  }
}


# Lambda function to scale ECS service to 0 (pause) or restore (resume)
data "archive_file" "ecs_scheduler" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/ecs_scheduler"
  output_path = "${path.module}/ecs_scheduler.zip"
}

resource "aws_lambda_function" "ecs_scheduler" {
  filename         = data.archive_file.ecs_scheduler.output_path
  function_name    = "${local.project_name}-ecs-scheduler"
  role             = aws_iam_role.ecs_scheduler.arn
  handler          = "lambda_function.handler"
  source_code_hash = data.archive_file.ecs_scheduler.output_base64sha256
  runtime          = "python3.11"
  timeout          = 60

  environment {
    variables = {
      CLUSTER_NAME = aws_ecs_cluster.main.name
      SERVICE_NAME = aws_ecs_service.backend.name
      MIN_CAPACITY = var.ecs_min_capacity
      MAX_CAPACITY = var.ecs_max_capacity
      PROJECT_NAME = local.project_name
      ENVIRONMENT  = var.environment
    }
  }

  # X-Ray distributed tracing
  tracing_config {
    mode = var.enable_xray_tracing ? "Active" : "PassThrough"
  }

  tags = {
    Name    = "${local.project_name}-ecs-scheduler"
    Purpose = "Auto Scale ECS Service (Pause/Resume)"
  }
}

# CloudWatch Log Group for Scheduler Lambda
resource "aws_cloudwatch_log_group" "ecs_scheduler" {
  name              = "/aws/lambda/${local.project_name}-ecs-scheduler"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${local.project_name}-ecs-scheduler-logs"
  }
}

# Lambda Permission: Allow EventBridge to invoke (Pause)
resource "aws_lambda_permission" "allow_eventbridge_pause" {
  count = var.environment == "dev" ? 1 : 0

  statement_id  = "AllowEventBridgePause"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ecs_scheduler.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.pause_ecs[0].arn
}

# Lambda Permission: Allow EventBridge to invoke (Resume)
resource "aws_lambda_permission" "allow_eventbridge_resume" {
  count = var.environment == "dev" ? 1 : 0

  statement_id  = "AllowEventBridgeResume"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ecs_scheduler.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.resume_ecs[0].arn
}
