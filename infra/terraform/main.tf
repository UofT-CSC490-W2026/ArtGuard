terraform {
  required_version = ">= 1.10.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.9"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
    }
  }

  # Remote state backend configuration
  backend "s3" {
    bucket         = "artguard-terraform-state"
    region         = "ca-central-1"
    encrypt        = true
    dynamodb_table = "artguard-terraform-locks"
    # Key is specified per environment using -backend-config flag:
    #   Dev:  terraform init -backend-config=backend-dev.hcl
    #   Prod: terraform init -backend-config=backend-prod.hcl
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = local.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# Provider alias for us-east-1 (required for CloudFront ACM certificates)
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = {
      Project     = local.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# Data source for current AWS account ID
data "aws_caller_identity" "current" {}

locals {
  project_name = "artguard"
}
