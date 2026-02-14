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
  }

  # Remote state backend configuration
  backend "s3" {
    bucket         = "artguard-terraform-state"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "artguard-terraform-locks"
    # Key is specified per environment using -backend-config flag:
    #   Dev:  terraform init -backend-config="key=dev/terraform.tfstate" -var-file=dev.tfvars
    #   Prod: terraform init -backend-config="key=prod/terraform.tfstate" -var-file=prod.tfvars
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
