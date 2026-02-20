# Backend configuration for prod environment
# Usage: terraform init -backend-config=backend-prod.hcl

bucket         = "artguard-terraform-state"
key            = "prod/terraform.tfstate"
region         = "ca-central-1"
encrypt        = true
dynamodb_table = "artguard-terraform-locks"
