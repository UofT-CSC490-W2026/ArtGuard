# DynamoDB Tables
# 4 tables: Users, InferenceRecords, ImageRecords, PatchRecords

# Table 1: Users
resource "aws_dynamodb_table" "users" {
  name           = "${local.project_name}-users-${var.environment}"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "user_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "email"
    type = "S"
  }

  # GSI for querying by email (login/lookup)
  global_secondary_index {
    name            = "EmailIndex"
    hash_key        = "email"
    projection_type = "ALL"
  }

  # Point-in-time recovery for prod
  point_in_time_recovery {
    enabled = var.environment == "prod"
  }

  # Encryption at rest
  server_side_encryption {
    enabled = true
  }

  tags = {
    Name        = "${local.project_name}-users"
    Environment = var.environment
  }
}

# Table 2: InferenceRecords
resource "aws_dynamodb_table" "inference_records" {
  name           = "${local.project_name}-inference-records-${var.environment}"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "inference_id"

  attribute {
    name = "inference_id"
    type = "S"
  }

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "N"  # Unix timestamp in milliseconds
  }

  # GSI for querying user's inferences (sorted by time)
  global_secondary_index {
    name            = "UserInferencesIndex"
    hash_key        = "user_id"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  # TTL for auto-cleanup (delete old inferences after 90 days)
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = var.environment == "prod"
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Name        = "${local.project_name}-inference-records"
    Environment = var.environment
  }
}

# Table 3: ImageRecords
resource "aws_dynamodb_table" "image_records" {
  name           = "${local.project_name}-image-records-${var.environment}"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "image_id"

  attribute {
    name = "image_id"
    type = "S"
  }

  attribute {
    name = "label"
    type = "S"
  }

  attribute {
    name = "split"
    type = "S"
  }

  # GSI for querying images by label+split (e.g., all "authentic" images in "train" set)
  global_secondary_index {
    name            = "LabelSplitIndex"
    hash_key        = "label"
    range_key       = "split"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = var.environment == "prod"
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Name        = "${local.project_name}-image-records"
    Environment = var.environment
  }
}

# Table 4: PatchRecords
resource "aws_dynamodb_table" "patch_records" {
  name           = "${local.project_name}-patch-records-${var.environment}"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "patch_id"

  attribute {
    name = "patch_id"
    type = "S"
  }

  attribute {
    name = "image_id"
    type = "S"
  }

  attribute {
    name = "patch_type"
    type = "S"
  }

  # GSI for querying all patches belonging to an image
  global_secondary_index {
    name            = "ImagePatchesIndex"
    hash_key        = "image_id"
    range_key       = "patch_type"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = var.environment == "prod"
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Name        = "${local.project_name}-patch-records"
    Environment = var.environment
  }
}
