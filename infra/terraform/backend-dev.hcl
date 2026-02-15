# Backend configuration for dev environment
# Usage: terraform init -backend-config=backend-dev.hcl

bucket         = "artguard-terraform-state"
key            = "dev/terraform.tfstate"
region         = "ca-central-1"
encrypt        = true
dynamodb_table = "artguard-terraform-locks"
