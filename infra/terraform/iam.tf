
# ECS Fargate IAM Roles

# ECS Execution Role (Pull images from ECR, retrieve secrets)
resource "aws_iam_role" "ecs_execution" {
  name = "${local.project_name}-ecs-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name = "${local.project_name}-ecs-execution-role"
  }
}

# ECS task execution
resource "aws_iam_role_policy_attachment" "ecs_execution_policy" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# ECS Execution to access Secrets Manager
resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name = "${local.project_name}-ecs-execution-secrets-policy"
  role = aws_iam_role.ecs_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          "${aws_secretsmanager_secret.modal_api_key.arn}*"
        ]
      }
    ]
  })
}

# ECS Task Role (Runtime permissions for the application)
resource "aws_iam_role" "ecs_task" {
  name = "${local.project_name}-ecs-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name = "${local.project_name}-ecs-task-role"
  }
}

# Attach ECS task role policy with S3, DynamoDB, Bedrock, and CloudWatch permissions
resource "aws_iam_role_policy_attachment" "ecs_task_policy" {
  role       = aws_iam_role.ecs_task.name
  policy_arn = aws_iam_policy.ecs_task_policy.arn
}

# Create custom policy for ECS task
resource "aws_iam_policy" "ecs_task_policy" {
  name        = "${local.project_name}-ecs-task-policy"
  description = "Policy for ECS tasks to access AWS services"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # S3 Access
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.images_raw.arn,
          "${aws_s3_bucket.images_raw.arn}/*",
          aws_s3_bucket.images_processed.arn,
          "${aws_s3_bucket.images_processed.arn}/*"
        ]
      },
      # DynamoDB Access
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:BatchGetItem",
          "dynamodb:BatchWriteItem"
        ]
        Resource = [
          aws_dynamodb_table.users.arn,
          "${aws_dynamodb_table.users.arn}/index/*",
          aws_dynamodb_table.inference_records.arn,
          "${aws_dynamodb_table.inference_records.arn}/index/*",
          aws_dynamodb_table.image_records.arn,
          "${aws_dynamodb_table.image_records.arn}/index/*",
          aws_dynamodb_table.patch_records.arn,
          "${aws_dynamodb_table.patch_records.arn}/index/*",
          aws_dynamodb_table.run_records.arn,
          "${aws_dynamodb_table.run_records.arn}/index/*",
          aws_dynamodb_table.config_records.arn,
          "${aws_dynamodb_table.config_records.arn}/index/*"
        ]
      },
      # Bedrock Access
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = "*"
      },
      # Bedrock Knowledge Base Access
      {
        Effect = "Allow"
        Action = [
          "bedrock:Retrieve",
          "bedrock:RetrieveAndGenerate"
        ]
        Resource = aws_bedrockagent_knowledge_base.main.arn
      },
      # CloudWatch Logs
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.ecs.arn}:*"
      }
    ]
  })
}

# X-Ray policy for ECS tasks (conditional)
resource "aws_iam_role_policy" "ecs_task_xray" {
  count = var.enable_xray_tracing ? 1 : 0

  name = "${local.project_name}-ecs-task-xray-policy"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords",
          "xray:GetSamplingRules",
          "xray:GetSamplingTargets",
          "xray:GetSamplingStatisticSummaries"
        ]
        Resource = "*"
      }
    ]
  })
}

# ECS Exec policy (for debugging in dev)
resource "aws_iam_role_policy" "ecs_exec" {
  count = var.environment == "dev" ? 1 : 0

  name = "${local.project_name}-ecs-exec-policy"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ssmmessages:CreateControlChannel",
          "ssmmessages:CreateDataChannel",
          "ssmmessages:OpenControlChannel",
          "ssmmessages:OpenDataChannel"
        ]
        Resource = "*"
      }
    ]
  })
}

# Bedrock Knowledge Base IAM Role 
resource "aws_iam_role" "bedrock_knowledge_base" {
  name = "${local.project_name}-bedrock-kb-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "bedrock.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name = "${local.project_name}-bedrock-kb-role"
  }
}

# Policy for S3 access (read documents)
resource "aws_iam_role_policy" "bedrock_kb_s3_access" {
  name = "${local.project_name}-bedrock-kb-s3-policy"
  role = aws_iam_role.bedrock_knowledge_base.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.knowledge_base.arn,
          "${aws_s3_bucket.knowledge_base.arn}/*"
        ]
      }
    ]
  })
}

# Policy for OpenSearch/Vector DB access
resource "aws_iam_role_policy" "bedrock_kb_opensearch_access" {
  name = "${local.project_name}-bedrock-kb-opensearch-policy"
  role = aws_iam_role.bedrock_knowledge_base.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "aoss:APIAccessAll"
        ]
        Resource = aws_opensearchserverless_collection.knowledge_base.arn
      }
    ]
  })
}

# Policy for Bedrock model access 
resource "aws_iam_role_policy" "bedrock_kb_model_access" {
  name = "${local.project_name}-bedrock-kb-model-policy"
  role = aws_iam_role.bedrock_knowledge_base.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v1"
      }
    ]
  })
}

