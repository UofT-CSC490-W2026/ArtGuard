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

# JWT signing secret for API auth (HS256). Replace value in AWS Console after apply.
resource "aws_secretsmanager_secret" "jwt_secret" {
  name                    = "${local.project_name}/jwt-secret-${var.environment}"
  description             = "JWT signing secret for /auth (HS256)"
  recovery_window_in_days = var.secrets_recovery_window_days

  tags = {
    Name        = "${local.project_name}-jwt-secret"
    Environment = var.environment
  }
}

resource "aws_secretsmanager_secret_version" "jwt_secret" {
  secret_id     = aws_secretsmanager_secret.jwt_secret.id
  secret_string = "REPLACE_WITH_LONG_RANDOM_STRING"

  lifecycle {
    ignore_changes = [secret_string]
  }
}
