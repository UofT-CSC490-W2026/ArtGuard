# Terraform Guide

## Table of Contents

1. [Where Outputs Are Saved](#where-outputs-are-saved)
2. [Why Bootstrap is Necessary](#why-bootstrap-is-necessary)
3. [Why S3 + DynamoDB for State](#why-s3--dynamodb-for-state)
4. [How State Works](#how-state-works)
5. [State Locking Explained](#state-locking-explained)
5. [Terraform Commands](#terraform-commands)

---

## Where Outputs Are Saved

When Terraform creates infrastructure, it generates outputs (URLs, IDs, etc.). These are saved in **3 locations**:

### 1. Terraform State File (Primary Source)

**Location:** `s3://artguard-terraform-state/dev/terraform.tfstate`

```json
{
  "version": 4,
  "terraform_version": "1.10.0",
  "outputs": {
    "backend_url": {
      "value": "http://artguard-alb-dev-123456789.ca-central-1.elb.amazonaws.com",
      "type": "string"
    },
    "cloudfront_distribution_url": {
      "value": "https://d1a2b3c4d5e6f7.cloudfront.net",
      "type": "string"
    },
    "ecr_repository_url": {
      "value": "123456789012.dkr.ecr.ca-central-1.amazonaws.com/artguard-backend",
      "type": "string"
    }
  },
  "resources": [...] // All infrastructure details
}
```

**Access:**
```bash
# View all outputs
terraform output

# Get specific output
terraform output -raw backend_url

# Get JSON format
terraform output -json > outputs.json
```

### 2. GitHub Actions Artifacts

**Location:** GitHub UI → Actions → Workflow run → Artifacts

When the bootstrap workflow runs, it saves `outputs.json` as an artifact:

```yaml
- name: Upload outputs artifact
  uses: actions/upload-artifact@v4
  with:
    name: terraform-outputs-dev
    path: infra/terraform/outputs.json
    retention-days: 30  # Stored for 30 days
```

**Access:**
1. Go to GitHub repository
2. Click **Actions** tab
3. Select **Terraform Bootstrap** workflow run
4. Scroll to **Artifacts** section
5. Download `terraform-outputs-dev.zip`
6. Extract and view `outputs.json`

### 3. GitHub Actions Logs

**Location:** GitHub UI → Actions → Workflow run → Logs

The outputs are printed to the console during the workflow:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Bootstrap Complete!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Key Outputs:

Frontend URL:
https://d1a2b3c4d5e6f7.cloudfront.net

Backend API (ALB):
http://artguard-alb-dev-123456789.ca-central-1.elb.amazonaws.com

S3 Frontend Bucket:
artguard-frontend-dev

CloudFront Distribution ID:
E1A2B3C4D5E6F7

ECR Repository:
123456789012.dkr.ecr.ca-central-1.amazonaws.com/artguard-backend
```

**Access:**
1. Go to GitHub Actions workflow run
2. Click on any job step
3. View the console output
4. Copy URLs directly from logs

### Summary: Where to Find Outputs

| Location | Permanent? | How to Access |
|----------|-----------|---------------|
| **S3 State File** | Yes | `terraform output` (requires AWS access) |
| **GitHub Artifact** | 30 days | Download from Actions → Artifacts |
| **GitHub Logs** | 90 days | View in Actions → Workflow logs |

---

## Why Bootstrap is Necessary

The bootstrap workflow/script is **required for first-time setup** because it performs special initialization steps that normal Terraform commands don't handle.

### What Makes Bootstrap Special

#### Creates the Backend Storage

**The Problem:**
```
Terraform needs:  S3 bucket to store state
But to create:    S3 bucket, you need Terraform
And Terraform:    Needs state storage to run!
```

**The Solution:**
```bash
# Bootstrap creates backend infrastructure FIRST
aws s3api create-bucket --bucket artguard-terraform-state
aws dynamodb create-table --table-name artguard-terraform-locks

# THEN initializes Terraform to use it
terraform init -backend-config=backend-dev.hcl
```
#### Safety Confirmations

Bootstrap includes safety checks:
```bash
# Check if environment already bootstrapped
if state file exists:
  ⚠️ Warning: Environment may already exist
  Prompt: Continue anyway?

# Require explicit confirmation
Type "BOOTSTRAP" to confirm
```

Prevents accidentally:
- Overwriting existing infrastructure
- Creating duplicate resources
- Destroying production by mistake

### When to Use Bootstrap

| Scenario | Use Bootstrap? | Use Normal Deploy? |
|----------|----------------|-------------------|
| **First-time setup (dev)** | ✅ Yes | ❌ No |
| **First-time setup (prod)** | ✅ Yes | ❌ No |
| **Update existing infrastructure** | ❌ No | ✅ Yes |
| **Add new resources to .tf files** | ❌ No | ✅ Yes |
| **Destroyed everything, starting over** | ✅ Yes | ❌ No |

### Bootstrap vs Normal Deployment

```
Bootstrap (One-Time):
  ./scripts/bootstrap.sh dev
  ↓
  1. Create S3 bucket (backend storage)
  2. Create DynamoDB table (state locking)
  3. Initialize Terraform
  4. Create ALL infrastructure (60+ resources)
  5. Save outputs

Normal Deployment (Updates):
  ./scripts/terraform-deploy.sh dev apply
  ↓
  1. Terraform already initialized ✓
  2. Backend already exists ✓
  3. Apply only CHANGES to infrastructure
  4. Update state file
```

---
## Remote State (S3 + DynamoDB)

**Store state in AWS S3:**

```
S3 Bucket: artguard-terraform-state
├── dev/terraform.tfstate
└── prod/terraform.tfstate
```

**Configure in backend-dev.hcl:**
```hcl
bucket         = "artguard-terraform-state"
key            = "dev/terraform.tfstate"
region         = "ca-central-1"
encrypt        = true
dynamodb_table = "artguard-terraform-locks"
```


## How State Works

### State Lifecycle

```
1. First Run (Bootstrap):
   terraform init
     ↓
   Creates empty state file in S3
     ↓
   terraform apply
     ↓
   Creates infrastructure
     ↓
   Updates state with resource IDs

2. Subsequent Runs:
   terraform plan
     ↓
   Reads state from S3
   Compares state ↔ config ↔ reality
   Shows differences
     ↓
   terraform apply
     ↓
   Creates/updates/deletes resources
   Updates state file
```
---

##  Terraform Commands

### Basic Manual Terraform Workflow

```bash
# Navigate to Terraform directory
cd infra/terraform

# 1. Initialize (when connecting to backend for first time / switching between prod and dev environments)
terraform init -backend-config=backend-dev.hcl

# 2. Format code
terraform fmt -recursive

# 3. Validate configuration
terraform validate

# 4. Plan changes
terraform plan -var-file=dev.tfvars

# 5. Apply changes
terraform apply -var-file=dev.tfvars

# 6. View outputs
terraform output
```

### Viewing Infrastructure

```bash
# View all outputs
terraform output

# View specific output
terraform output -raw backend_url
terraform output -raw cloudfront_distribution_url
terraform output -raw ecr_repository_url

# View all outputs as JSON
terraform output -json

# Save outputs to file
terraform output -json > outputs.json

# List all resources
terraform state list

# View specific resource
terraform state show aws_ecs_service.backend

### View State File

# Download from S3
aws s3 cp s3://artguard-terraform-state/dev/terraform.tfstate .

# View in Terraform
terraform show
```

### Working with Different Environments

```bash
# Switch to dev environment
terraform init -backend-config=backend-dev.hcl
terraform workspace show  # Shows: default

# View dev outputs
terraform output

# Switch to prod environment
terraform init -backend-config=backend-prod.hcl

# View prod outputs
terraform output

# Always verify which environment you're in!
terraform output environment  # Should show: dev or prod
```

### Terraform Best Practices

```bash
# 1. ALWAYS format before committing
terraform fmt -recursive

# 2. ALWAYS validate
terraform validate

# 3. ALWAYS review plan before apply
terraform plan -var-file=dev.tfvars | less

# 4. NEVER commit .tfstate files
# (They're in .gitignore )

# 5. NEVER run apply without plan first
terraform plan -var-file=dev.tfvars -out=tfplan
terraform apply tfplan

# 6. ALWAYS use backend config files
terraform init -backend-config=backend-dev.hcl

# 7. NEVER store secrets in .tfvars files
# (Use Secrets Manager or environment variables)
```

---

**Related Docs:**
- [DEPLOYMENT.md](DEPLOYMENT.md) - Complete deployment guide
- [DEVELOPMENT.md](DEVELOPMENT.md) - Development commands and workflows
- [scripts/README.md](scripts/README.md) - Script documentation
