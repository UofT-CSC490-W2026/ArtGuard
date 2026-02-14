# DynamoDB Table: Image Analysis Results
resource "aws_dynamodb_table" "image_analysis" {
  name         = "${local.project_name}-image-analysis-${var.environment}"
  billing_mode = var.dynamodb_billing_mode

  # Primary Key
  hash_key  = "request_id"
  range_key = "created_at"

  # Primary Key Attributes
  attribute {
    name = "request_id"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "N"
  }

  # Attributes for GSI 
  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  # GSI: Query all images for a specific user
  global_secondary_index {
    name            = "user-index"
    hash_key        = "user_id"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  # GSI: Query images by status (e.g., all PENDING)
  global_secondary_index {
    name            = "status-index"
    hash_key        = "status"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  # Point-in-time recovery (backup)
  point_in_time_recovery {
    enabled = var.enable_dynamodb_pitr
  }

  # Encryption at rest
  server_side_encryption {
    enabled = true
  }

  tags = {
    Name    = "${local.project_name}-image-analysis"
    Purpose = "Forgery detection results and image analysis data"
  }
}

# DynamoDB Table: Users
resource "aws_dynamodb_table" "users" {
  name         = "${local.project_name}-users-${var.environment}"
  billing_mode = var.dynamodb_billing_mode

  # Primary Key
  hash_key = "user_id"

  # Primary Key Attribute
  attribute {
    name = "user_id"
    type = "S"
  }

  # Attribute for GSI
  attribute {
    name = "email"
    type = "S"
  }

  # GSI: Query user by email (for login/lookup)
  global_secondary_index {
    name            = "email-index"
    hash_key        = "email"
    projection_type = "ALL"
  }

  # Point-in-time recovery (backup)
  point_in_time_recovery {
    enabled = var.enable_dynamodb_pitr
  }

  # Encryption at rest
  server_side_encryption {
    enabled = true
  }

  tags = {
    Name    = "${local.project_name}-users"
    Purpose = "User accounts and profile data"
  }
}
