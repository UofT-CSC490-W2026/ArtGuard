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
