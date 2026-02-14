# AWS Secrets Manager

# Secret for Modal API Key (for ML model inference)
resource "aws_secretsmanager_secret" "modal_api_key" {
  name                    = "${local.project_name}/modal-api-key-${var.environment}"
  description             = "API key for Modal ML inference service"
  recovery_window_in_days = var.secrets_recovery_window_days

  tags = {
    Name        = "${local.project_name}-modal-api-key"
    Environment = var.environment
  }
}

# Secret version for Modal API Key
resource "aws_secretsmanager_secret_version" "modal_api_key" {
  secret_id     = aws_secretsmanager_secret.modal_api_key.id
  secret_string = "PLACEHOLDER"

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# Resource-Based Policy for Modal API Key Secret
# Restricts access to only ECS Execution Role (which retrieves secrets for ECS tasks)
resource "aws_secretsmanager_secret_policy" "modal_api_key" {
  secret_arn = aws_secretsmanager_secret.modal_api_key.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowECSExecutionAccess"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.ecs_execution.arn
        }
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = "*"
      },
      {
        Sid    = "AllowAccountRootAccess"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "secretsmanager:*"
        Resource = "*"
      },
      {
        Sid    = "DenyAllOthersGetValue"
        Effect = "Deny"
        NotPrincipal = {
          AWS = [
            aws_iam_role.ecs_execution.arn,
            "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
          ]
        }
        Action   = "secretsmanager:GetSecretValue"
        Resource = "*"
      }
    ]
  })
}
