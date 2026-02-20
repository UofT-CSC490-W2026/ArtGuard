# Project Configuration Variables
variable "environment" {
  description = "Environment name (dev or prod)"
  type        = string
  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "Environment must be dev or prod."
  }
}

variable "aws_region" {
  description = "AWS region for resource deployment"
  type        = string
  default     = "us-east-1" # TODO: Set to your preferred region (us-east-1, us-west-2, etc.)
}

# Domain Configuration (Route 53)
variable "domain_name" {
  description = "Custom domain name for the application"
  type        = string
  default     = "" # TODO: Set after registering domain in Route 53

  validation {
    condition     = var.domain_name == "" || can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]\\.[a-z]{2,}$", var.domain_name))
    error_message = "Domain name must be a valid domain"
  }
}

variable "enable_custom_domain" {
  description = "Enable custom domain setup with Route 53 (set to true after registering domain)"
  type        = bool
  default     = false # TODO: Set to true after domain registration
}

# ECS Fargate configuration is defined at the end of this file

# DynamoDB Configuration

variable "dynamodb_billing_mode" {
  description = "DynamoDB billing mode (PAY_PER_REQUEST or PROVISIONED)"
  type        = string
  default     = "PAY_PER_REQUEST"
  validation {
    condition     = contains(["PAY_PER_REQUEST", "PROVISIONED"], var.dynamodb_billing_mode)
    error_message = "Billing mode must be PAY_PER_REQUEST or PROVISIONED."
  }
}

variable "enable_dynamodb_pitr" {
  description = "Enable point-in-time recovery for DynamoDB"
  type        = bool
  default     = true
}

# S3 Configuration
variable "s3_lifecycle_glacier_days" {
  description = "Days before transitioning to Glacier storage"
  type        = number
  default     = 180
}

variable "s3_lifecycle_expiration_days" {
  description = "Days before expiring objects (0 = disabled)"
  type        = number
  default     = 0
}

# CloudWatch Configuration
variable "log_retention_days" {
  description = "CloudWatch Logs retention in days"
  type        = number
  default     = 30
  validation {
    condition = contains([
      1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180,
      365, 400, 545, 731, 1096, 1827, 2192, 2557,
      2922, 3288, 3653, 0
    ], var.log_retention_days)
    error_message = "Log retention must be a valid CloudWatch Logs retention value."
  }
}

# Feature Flags
variable "enable_xray_tracing" {
  description = "Enable AWS X-Ray for distributed tracing"
  type        = bool
  default     = false
}

# Bedrock Knowledge Base Configuration
variable "bedrock_embedding_model" {
  description = "Bedrock embedding model for Knowledge Base"
  type        = string
  default     = "amazon.titan-embed-text-v1"
}

variable "bedrock_chunking_strategy" {
  description = "Document chunking strategy for Knowledge Base"
  type        = string
  default     = "FIXED_SIZE"
  validation {
    condition     = contains(["FIXED_SIZE", "NONE"], var.bedrock_chunking_strategy)
    error_message = "Chunking strategy must be FIXED_SIZE or NONE."
  }
}

variable "bedrock_chunk_max_tokens" {
  description = "Maximum tokens per document chunk"
  type        = number
  default     = 300
  validation {
    condition     = var.bedrock_chunk_max_tokens >= 20 && var.bedrock_chunk_max_tokens <= 8000
    error_message = "Max tokens must be between 20 and 8000."
  }
}

variable "bedrock_chunk_overlap_percentage" {
  description = "Percentage overlap between chunks (prevents context loss)"
  type        = number
  default     = 20
  validation {
    condition     = var.bedrock_chunk_overlap_percentage >= 1 && var.bedrock_chunk_overlap_percentage <= 99
    error_message = "Overlap percentage must be between 1 and 99."
  }
}

variable "bedrock_vector_index_name" {
  description = "Name of the vector index in OpenSearch Serverless"
  type        = string
  default     = "bedrock-knowledge-base-index"
}

variable "bedrock_ingest_test_data" {
  description = "Whether to automatically upload and ingest test data into the Knowledge Base (creates the OpenSearch index)"
  type        = bool
  default     = false
}

# ECR Configuration
variable "ecr_image_retention_count" {
  description = "Number of tagged images to retain in ECR"
  type        = number
  default     = 10
  validation {
    condition     = var.ecr_image_retention_count >= 1 && var.ecr_image_retention_count <= 1000
    error_message = "Image retention count must be between 1 and 1000."
  }
}

variable "ecr_untagged_image_days" {
  description = "Days before deleting untagged images from ECR"
  type        = number
  default     = 7
  validation {
    condition     = var.ecr_untagged_image_days >= 1 && var.ecr_untagged_image_days <= 365
    error_message = "Untagged image retention must be between 1 and 365 days."
  }
}

variable "ecr_scan_on_push" {
  description = "Enable automatic image scanning on push to ECR"
  type        = bool
  default     = true
}

# S3 Lifecycle Configuration
variable "s3_inference_expiration_days" {
  description = "Days before deleting inference images (GDPR/privacy compliance)"
  type        = number
  default     = 30
  validation {
    condition     = var.s3_inference_expiration_days >= 1 && var.s3_inference_expiration_days <= 365
    error_message = "Inference expiration must be between 1 and 365 days."
  }
}

variable "s3_training_ia_transition_days" {
  description = "Days before transitioning training images to Standard-IA storage"
  type        = number
  default     = 90
  validation {
    condition     = var.s3_training_ia_transition_days >= 30 && var.s3_training_ia_transition_days <= 365
    error_message = "Standard-IA transition must be between 30 and 365 days."
  }
}

# Scheduler Configuration
variable "scheduler_pause_cron" {
  description = "Cron expression for pausing ECS (UTC timezone)"
  type        = string
  default     = "cron(0 3 * * ? *)" # 10 PM EST = 3 AM UTC
}

variable "scheduler_resume_cron" {
  description = "Cron expression for resuming ECS (UTC timezone)"
  type        = string
  default     = "cron(0 13 * * ? *)" # 8 AM EST = 1 PM UTC
}

# Secrets Manager Configuration
variable "secrets_recovery_window_days" {
  description = "Number of days AWS waits before permanently deleting a secret"
  type        = number
  default     = 7
  validation {
    condition     = var.secrets_recovery_window_days >= 7 && var.secrets_recovery_window_days <= 30
    error_message = "Recovery window must be between 7 and 30 days."
  }
}


# VPC and Networking Variables


variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "az_count" {
  description = "Number of availability zones to use (2 recommended for HA)"
  type        = number
  default     = 2
  validation {
    condition     = var.az_count >= 2 && var.az_count <= 3
    error_message = "AZ count must be between 2 and 3."
  }
}

variable "enable_vpc_endpoints" {
  description = "Enable VPC endpoints for AWS services (cost optimization)"
  type        = bool
  default     = true
}


# ECS Fargate Variables


variable "ecs_cpu" {
  description = "CPU units for ECS Fargate task (256, 512, 1024, 2048, 4096)"
  type        = number
  default     = 1024
  validation {
    condition     = contains([256, 512, 1024, 2048, 4096], var.ecs_cpu)
    error_message = "ECS CPU must be 256, 512, 1024, 2048, or 4096."
  }
}

variable "ecs_memory" {
  description = "Memory for ECS Fargate task in MB"
  type        = number
  default     = 2048
  validation {
    condition     = var.ecs_memory >= 512 && var.ecs_memory <= 30720
    error_message = "ECS memory must be between 512 and 30720 MB."
  }
}

variable "ecs_desired_count" {
  description = "Desired number of ECS tasks"
  type        = number
  default     = 1
}

variable "ecs_min_capacity" {
  description = "Minimum number of ECS tasks for auto scaling"
  type        = number
  default     = 1
}

variable "ecs_max_capacity" {
  description = "Maximum number of ECS tasks for auto scaling"
  type        = number
  default     = 10
}

variable "ecs_cpu_target" {
  description = "Target CPU utilization percentage for auto scaling"
  type        = number
  default     = 70
}

variable "ecs_memory_target" {
  description = "Target memory utilization percentage for auto scaling"
  type        = number
  default     = 80
}

variable "ecs_request_count_target" {
  description = "Target request count per task for auto scaling"
  type        = number
  default     = 1000
}

variable "use_fargate_spot" {
  description = "Use Fargate Spot for cost savings (can be interrupted)"
  type        = bool
  default     = false
}

variable "enable_container_insights" {
  description = "Enable CloudWatch Container Insights for ECS"
  type        = bool
  default     = true
}


# ALB Health Check Variables


variable "ecs_health_check_interval" {
  description = "Health check interval in seconds"
  type        = number
  default     = 30
}

variable "ecs_health_check_timeout" {
  description = "Health check timeout in seconds"
  type        = number
  default     = 5
}

variable "ecs_health_check_healthy_threshold" {
  description = "Number of consecutive successful health checks"
  type        = number
  default     = 2
}

variable "ecs_health_check_unhealthy_threshold" {
  description = "Number of consecutive failed health checks"
  type        = number
  default     = 3
}
