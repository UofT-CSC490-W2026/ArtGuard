# S3 Outputs
output "s3_frontend_bucket_name" {
  description = "Name of the frontend S3 bucket"
  value       = aws_s3_bucket.frontend.id
}

output "s3_frontend_bucket_arn" {
  description = "ARN of the frontend S3 bucket"
  value       = aws_s3_bucket.frontend.arn
}

output "s3_images_raw_bucket_name" {
  description = "Name of the raw images S3 bucket"
  value       = aws_s3_bucket.images_raw.id
}

output "s3_images_processed_bucket_name" {
  description = "Name of the processed images S3 bucket"
  value       = aws_s3_bucket.images_processed.id
}

# CloudFront Outputs
output "cloudfront_distribution_id" {
  description = "ID of the CloudFront distribution"
  value       = aws_cloudfront_distribution.frontend.id
}

output "cloudfront_distribution_domain" {
  description = "Domain name of the CloudFront distribution"
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "cloudfront_distribution_url" {
  description = "Full HTTPS URL of the CloudFront distribution"
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

# ECR Outputs
output "ecr_repository_url" {
  description = "URL of the ECR repository"
  value       = aws_ecr_repository.backend.repository_url
}

output "ecr_repository_arn" {
  description = "ARN of the ECR repository"
  value       = aws_ecr_repository.backend.arn
}

# DynamoDB Outputs
output "dynamodb_users_table_name" {
  description = "Name of the Users DynamoDB table"
  value       = aws_dynamodb_table.users.name
}

output "dynamodb_users_table_arn" {
  description = "ARN of the Users DynamoDB table"
  value       = aws_dynamodb_table.users.arn
}

output "dynamodb_inference_records_table_name" {
  description = "Name of the InferenceRecords DynamoDB table"
  value       = aws_dynamodb_table.inference_records.name
}

output "dynamodb_inference_records_table_arn" {
  description = "ARN of the InferenceRecords DynamoDB table"
  value       = aws_dynamodb_table.inference_records.arn
}

output "dynamodb_image_records_table_name" {
  description = "Name of the ImageRecords DynamoDB table"
  value       = aws_dynamodb_table.image_records.name
}

output "dynamodb_image_records_table_arn" {
  description = "ARN of the ImageRecords DynamoDB table"
  value       = aws_dynamodb_table.image_records.arn
}

output "dynamodb_patch_records_table_name" {
  description = "Name of the PatchRecords DynamoDB table"
  value       = aws_dynamodb_table.patch_records.name
}

output "dynamodb_patch_records_table_arn" {
  description = "ARN of the PatchRecords DynamoDB table"
  value       = aws_dynamodb_table.patch_records.arn
}

output "dynamodb_run_records_table_name" {
  description = "Name of the RunRecords DynamoDB table"
  value       = aws_dynamodb_table.run_records.name
}

output "dynamodb_run_records_table_arn" {
  description = "ARN of the RunRecords DynamoDB table"
  value       = aws_dynamodb_table.run_records.arn
}

output "dynamodb_config_records_table_name" {
  description = "Name of the ConfigRecords DynamoDB table"
  value       = aws_dynamodb_table.config_records.name
}

output "dynamodb_config_records_table_arn" {
  description = "ARN of the ConfigRecords DynamoDB table"
  value       = aws_dynamodb_table.config_records.arn
}

# Bedrock Knowledge Base Outputs
output "knowledge_base_id" {
  description = "ID of the Bedrock Knowledge Base for RAG"
  value       = aws_bedrockagent_knowledge_base.main.id
}

output "knowledge_base_arn" {
  description = "ARN of the Bedrock Knowledge Base"
  value       = aws_bedrockagent_knowledge_base.main.arn
}

output "knowledge_base_s3_bucket" {
  description = "S3 bucket name for Knowledge Base documents"
  value       = aws_s3_bucket.knowledge_base.id
}

output "opensearch_collection_endpoint" {
  description = "OpenSearch Serverless collection endpoint"
  value       = aws_opensearchserverless_collection.knowledge_base.collection_endpoint
}

output "opensearch_collection_arn" {
  description = "ARN of OpenSearch Serverless collection"
  value       = aws_opensearchserverless_collection.knowledge_base.arn
}

output "knowledge_base_data_source_id" {
  description = "ID of the Knowledge Base data source (S3)"
  value       = aws_bedrockagent_data_source.s3_documents.id
}

# Secrets Manager Outputs
output "modal_api_key_secret_arn" {
  description = "ARN of the Modal API Key secret"
  value       = aws_secretsmanager_secret.modal_api_key.arn
  sensitive   = true
}

# CloudWatch Outputs
output "cloudwatch_dashboard_name" {
  description = "Name of the CloudWatch dashboard"
  value       = aws_cloudwatch_dashboard.main.dashboard_name
}


# Route 53 & Custom Domain Outputs
output "domain_name" {
  description = "Custom domain name (if enabled)"
  value       = var.enable_custom_domain ? var.domain_name : null
}

output "hosted_zone_id" {
  description = "Route 53 hosted zone ID (if custom domain enabled)"
  value       = var.enable_custom_domain ? aws_route53_zone.main[0].zone_id : null
}

output "hosted_zone_name_servers" {
  description = "Name servers for the hosted zone (point your domain to these)"
  value       = var.enable_custom_domain ? aws_route53_zone.main[0].name_servers : []
}

output "frontend_custom_url" {
  description = "Custom domain URL for frontend (if enabled)"
  value       = var.enable_custom_domain ? "https://${var.domain_name}" : null
}

output "frontend_www_url" {
  description = "WWW subdomain URL for frontend (if enabled)"
  value       = var.enable_custom_domain ? "https://www.${var.domain_name}" : null
}

output "backend_custom_url" {
  description = "Custom domain URL for backend API (if enabled)"
  value       = var.enable_custom_domain ? "https://api.${var.domain_name}" : null
}

output "acm_certificate_cloudfront_arn" {
  description = "ARN of CloudFront ACM certificate (if custom domain enabled)"
  value       = var.enable_custom_domain ? aws_acm_certificate.cloudfront[0].arn : null
}

# VPC Outputs

output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.main.id
}

output "vpc_cidr" {
  description = "CIDR block of the VPC"
  value       = aws_vpc.main.cidr_block
}

output "public_subnet_ids" {
  description = "IDs of the public subnets"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "IDs of the private subnets"
  value       = aws_subnet.private[*].id
}

output "nat_gateway_ids" {
  description = "IDs of the NAT Gateways"
  value       = aws_nat_gateway.main[*].id
}

# ALB Outputs

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = aws_lb.backend.dns_name
}

output "alb_arn" {
  description = "ARN of the Application Load Balancer"
  value       = aws_lb.backend.arn
}

output "alb_zone_id" {
  description = "Zone ID of the Application Load Balancer"
  value       = aws_lb.backend.zone_id
}

output "alb_target_group_arn" {
  description = "ARN of the ALB target group"
  value       = aws_lb_target_group.backend.arn
}

output "alb_security_group_id" {
  description = "Security group ID for the ALB"
  value       = aws_security_group.alb.id
}

# ECS Outputs

output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = aws_ecs_cluster.main.name
}

output "ecs_cluster_arn" {
  description = "ARN of the ECS cluster"
  value       = aws_ecs_cluster.main.arn
}

output "ecs_service_name" {
  description = "Name of the ECS service"
  value       = aws_ecs_service.backend.name
}

output "ecs_service_arn" {
  description = "ARN of the ECS service"
  value       = aws_ecs_service.backend.id
}

output "ecs_task_definition_arn" {
  description = "ARN of the ECS task definition"
  value       = aws_ecs_task_definition.backend.arn
}

output "ecs_task_security_group_id" {
  description = "Security group ID for ECS tasks"
  value       = aws_security_group.ecs_tasks.id
}

output "ecs_execution_role_arn" {
  description = "ARN of the ECS execution role"
  value       = aws_iam_role.ecs_execution.arn
}

output "ecs_task_role_arn" {
  description = "ARN of the ECS task role"
  value       = aws_iam_role.ecs_task.arn
}

# Scheduler Outputs

output "scheduler_pause_time" {
  description = "Time when ECS service pauses (saves money)"
  value       = "10:00 PM EST daily (03:00 UTC)"
}

output "scheduler_resume_time" {
  description = "Time when ECS service resumes"
  value       = "8:00 AM EST daily (13:00 UTC)"
}

output "summary" {
  description = "Quick summary of key resources"
  value = {
    # Frontend URLs
    frontend_url        = var.enable_custom_domain ? "https://${var.domain_name}" : "https://${aws_cloudfront_distribution.frontend.domain_name}"
    frontend_www_url    = var.enable_custom_domain ? "https://www.${var.domain_name}" : null
    frontend_cloudfront = "https://${aws_cloudfront_distribution.frontend.domain_name}"

    # Backend URLs
    backend_url     = var.enable_custom_domain ? "https://api.${var.domain_name}" : "http://${aws_lb.backend.dns_name}"
    backend_alb_dns = aws_lb.backend.dns_name

    # Compute Infrastructure
    ecs_cluster_name  = aws_ecs_cluster.main.name
    ecs_service_name  = aws_ecs_service.backend.name
    ecr_repository    = aws_ecr_repository.backend.repository_url
    alb_dns_name      = aws_lb.backend.dns_name

    # Storage
    frontend_bucket          = aws_s3_bucket.frontend.id
    images_raw_bucket        = aws_s3_bucket.images_raw.id
    dynamodb_users_table     = aws_dynamodb_table.users.name
    dynamodb_inferences_table = aws_dynamodb_table.inference_records.name
    dynamodb_images_table    = aws_dynamodb_table.image_records.name
    dynamodb_patches_table   = aws_dynamodb_table.patch_records.name
    dynamodb_runs_table      = aws_dynamodb_table.run_records.name
    dynamodb_configs_table   = aws_dynamodb_table.config_records.name

    # Bedrock RAG
    knowledge_base_id = aws_bedrockagent_knowledge_base.main.id
    knowledge_base_s3 = aws_s3_bucket.knowledge_base.id

    # Networking
    vpc_id              = aws_vpc.main.id
    public_subnet_ids   = aws_subnet.public[*].id
    private_subnet_ids  = aws_subnet.private[*].id

    # Domain
    custom_domain = var.enable_custom_domain ? var.domain_name : "Not configured"

    # Configuration
    region      = var.aws_region
    environment = var.environment
  }
}
