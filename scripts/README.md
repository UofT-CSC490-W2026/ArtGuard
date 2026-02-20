## Deployment Scripts

These scripts can be run **locally from CLI** or **from GitHub Actions workflows**.

All scripts support both environments with the same commands.

## Table of Contents
1. [Quick Reference](#quick-reference)
2. [Detailed Documentation](#detailed-documentation)
4. [Github Actions](#github-actions-integration)

---

## Quick Reference

### **Build & Deploy Backend**
```bash
# 1. Build and push Docker image
./scripts/build-and-push-docker.sh dev

# 2. Deploy to ECS
./scripts/deploy-ecs.sh dev
```

### **Infrastructure Management**
```bash
# Initialize Terraform (first time only)
./scripts/terraform-deploy.sh dev init

# Plan changes
./scripts/terraform-deploy.sh dev plan

# Apply changes
./scripts/terraform-deploy.sh dev apply

# Destroy everything (careful!)
./scripts/terraform-deploy.sh dev destroy
```

### **ECS Service Control**
```bash
# Force new deployment
./scripts/ecs-control.sh deploy dev

# Scale service
./scripts/ecs-control.sh scale dev 2    # Scale to 2 tasks
./scripts/ecs-control.sh scale dev 0    # Pause (scale to 0)

# Check status
./scripts/ecs-control.sh status dev

# View logs
./scripts/ecs-control.sh logs dev
```

### **Frontend Deployment**
```bash
# Deploy React frontend to S3 + CloudFront
./scripts/deploy-frontend.sh dev
```

### **Knowledge Base**
```bash
# Update Bedrock Knowledge Base with docs
./scripts/update-knowledge-base.sh dev ./docs
```

### **Bootstrap (First-Time Setup)**
```bash
# One-time infrastructure setup
./scripts/bootstrap.sh dev
```

### **Terraform Validation**
```bash
# Validate Terraform config (for PRs)
./scripts/terraform-validate.sh dev
```

### **Setup Secrets**
```bash
# Set Modal API key in Secrets Manager
./scripts/setup-secrets.sh dev
```

---

## Detailed Documentation

### All Available Scripts

| Script | Purpose | Type |
|--------|---------|------|
| **build-and-push-docker.sh** | Build Docker image and push to ECR | Backend |
| **deploy-ecs.sh** | Force ECS service deployment | Backend |
| **deploy-frontend.sh** | Build React and deploy to S3/CloudFront | Frontend |
| **bootstrap.sh** | One-time infrastructure setup | Infrastructure |
| **terraform-deploy.sh** | Apply Terraform changes | Infrastructure |
| **terraform-validate.sh** | Validate Terraform config (PRs) | Infrastructure |
| **ecs-control.sh** | Manual ECS service control | Operations |
| **setup-secrets.sh** | Upload secrets to Secrets Manager | Configuration |
| **update-knowledge-base.sh** | Sync docs to Bedrock Knowledge Base | AI/RAG |

---

### **build-and-push-docker.sh**
Builds Docker image and pushes to ECR.

**Usage:**
```bash
./scripts/build-and-push-docker.sh [environment]
```

**Environment Variables:**
- `AWS_REGION` - AWS region (default: ca-central-1)
- `ECR_REPOSITORY` - ECR repository name (default: artguard-backend)

**What it does:**
1. Generates semantic version tag (vYYYY.MM.DD-SHA-BUILD)
2. Logs into ECR
3. Builds Docker image with proper platform (linux/amd64)
4. Pushes both versioned tag and :latest

**Example:**
```bash
AWS_REGION=ca-central-1 ./scripts/build-and-push-docker.sh dev
```

---

### **deploy-ecs.sh**
Forces ECS service to deploy latest Docker image.

**Usage:**
```bash
./scripts/deploy-ecs.sh [environment]
```

**Environment Variables:**
- `AWS_REGION` - AWS region (default: ca-central-1)
- `ECS_CLUSTER` - ECS cluster name (default: artguard-cluster)
- `ECS_SERVICE` - ECS service name (default: artguard-backend)

**What it does:**
1. Calls `aws ecs update-service --force-new-deployment`
2. Triggers rolling deployment with health checks
3. Takes ~2-3 minutes to complete

**Example:**
```bash
./scripts/deploy-ecs.sh dev
```

---

### **ecs-control.sh**
Manual control over ECS service.

**Usage:**
```bash
./scripts/ecs-control.sh [action] [environment] [desired_count]
```

**Actions:**
- `deploy` - Force new deployment
- `scale` - Change desired task count
- `status` - Check service health
- `logs` - View recent CloudWatch logs

**Examples:**
```bash
# Force deployment
./scripts/ecs-control.sh deploy dev

# Scale to 2 tasks
./scripts/ecs-control.sh scale dev 2

# Pause service (save costs)
./scripts/ecs-control.sh scale dev 0

# Resume service
./scripts/ecs-control.sh scale dev 1

# Check health
./scripts/ecs-control.sh status dev

# View logs
./scripts/ecs-control.sh logs dev
```

---

### **terraform-deploy.sh**
Terraform infrastructure deployment.

**Usage:**
```bash
./scripts/terraform-deploy.sh [environment] [action]
```

**Actions:**
- `init` - Initialize backend (run first time)
- `plan` - Preview changes
- `apply` - Apply changes
- `destroy` - Destroy infrastructure

**Examples:**
```bash
# First time setup
./scripts/terraform-deploy.sh dev init

# Preview changes
./scripts/terraform-deploy.sh dev plan

# Apply changes
./scripts/terraform-deploy.sh dev apply

# Production deployment
./scripts/terraform-deploy.sh prod init
./scripts/terraform-deploy.sh prod plan
./scripts/terraform-deploy.sh prod apply
```

---

### **setup-secrets.sh**
Upload secrets to AWS Secrets Manager.

**Usage:**
```bash
./scripts/setup-secrets.sh [environment]
```

**What it does:**
1. Prompts for Modal API key (hidden input)
2. Uploads to Secrets Manager
3. ECS tasks automatically retrieve on startup

**Example:**
```bash
./scripts/setup-secrets.sh dev
# Enter Modal API Key: ************
```

---

### **deploy-frontend.sh**
Builds React application and deploys to S3 + CloudFront.

**Usage:**
```bash
./scripts/deploy-frontend.sh [environment]
```

**Environment Variables:**
- `AWS_REGION` - AWS region (default: ca-central-1)
- `NODE_ENV` - Node environment (set to production)
- `REACT_APP_ENVIRONMENT` - React app environment variable

**What it does:**
1. Cleans previous builds
2. Installs npm dependencies with `npm ci`
3. Builds React production bundle
4. Syncs static assets to S3 with long cache (31536000s)
5. Syncs HTML/JSON with short cache (0s, must-revalidate)
6. Invalidates CloudFront cache for immediate updates
7. Takes ~5-10 minutes total

**Examples:**
```bash
# Deploy to dev
./scripts/deploy-frontend.sh dev

# Deploy to prod
./scripts/deploy-frontend.sh prod
```

**Output:**
- S3 Bucket: `artguard-frontend-{environment}`
- CloudFront: Automatically invalidated
- Live in ~2-5 minutes after invalidation

---

### **bootstrap.sh**
One-time infrastructure setup for new environments.

**Usage:**
```bash
./scripts/bootstrap.sh [environment]
```

**Environment Variables:**
- `AWS_REGION` - AWS region (default: ca-central-1)

**What it does:**
1. Creates S3 bucket for Terraform state (if not exists)
2. Creates DynamoDB table for state locking (if not exists)
3. Initializes Terraform backend
4. Validates Terraform configuration
5. Creates Terraform plan
6. Applies all infrastructure resources (~60+ resources)
7. Displays key outputs (Frontend URL, Backend URL, etc.)

**Safety Features:**
- Requires typing "BOOTSTRAP" to confirm
- Checks if environment already exists
- Prompts before applying changes
- Cannot be run accidentally

**Examples:**
```bash
# Bootstrap dev environment (first time)
./scripts/bootstrap.sh dev

# Bootstrap prod environment (first time)
./scripts/bootstrap.sh prod
```

**When to Use:**
- First-time setup for dev environment
- First-time setup for prod environment
- Recreating destroyed infrastructure
- DO NOT use for regular updates (use terraform-deploy.sh instead)

**Duration:** ~15-20 minutes

---

### **terraform-validate.sh**
Validates Terraform configuration for Pull Requests and manual checks.

**Usage:**
```bash
./scripts/terraform-validate.sh [environment]
```

**Environment Variables:**
- `AWS_REGION` - AWS region (default: ca-central-1)

**What it does:**
1. Checks Terraform formatting (`terraform fmt -check`)
2. Runs TFLint if installed (optional linting)
3. Initializes Terraform backend
4. Validates Terraform syntax and configuration
5. Creates Terraform plan (without applying)
6. Saves plan to `tfplan` file

**Examples:**
```bash
# Validate dev configuration
./scripts/terraform-validate.sh dev

# Validate prod configuration
./scripts/terraform-validate.sh prod
```

**Use Cases:**
- Before creating Pull Requests
- Manual validation before applying changes
- CI/CD validation in GitHub Actions
- Checking if Terraform changes are valid

**Output:**
- Shows formatting issues (if any)
- Shows validation errors (if any)
- Shows plan preview (what would change)
- Saves plan to `tfplan` for later apply

---

### **update-knowledge-base.sh**
Updates Bedrock Knowledge Base with documentation for RAG.

**Usage:**
```bash
./scripts/update-knowledge-base.sh [environment] [docs_directory]
```

**Environment Variables:**
- `AWS_REGION` - AWS region (default: ca-central-1)

**What it does:**
1. Validates docs directory exists
2. Counts documents (.txt, .md, .pdf, .docx)
3. Syncs documents to S3 (`artguard-knowledge-base-{env}`)
4. Triggers Bedrock ingestion job (if available)
5. Creates embeddings for RAG queries
6. Takes ~2-10 minutes depending on document count

**Supported Formats:**
- `.txt` - Plain text
- `.md` - Markdown
- `.pdf` - PDF documents
- `.docx` - Microsoft Word

**Examples:**
```bash
# Update dev knowledge base with docs folder
./scripts/update-knowledge-base.sh dev ./docs

# Update prod knowledge base
./scripts/update-knowledge-base.sh prod ./docs

# Update with different directory
./scripts/update-knowledge-base.sh dev ./documentation
```

**Output:**
- S3 Bucket: `artguard-knowledge-base-{environment}`
- S3 Prefix: `documents/`
- Ingestion: Automatic (2-10 minutes)

**Use Cases:**
- Refreshing knowledge base content
- Initial setup of RAG system

---

## GitHub Actions Integration

All scripts are designed to work both locally and in GitHub Actions:

| Workflow | Scripts Used | Trigger |
|----------|-------------|---------|
| **app-docker.yml** | `build-and-push-docker.sh` + `deploy-ecs.sh` | Push to `dev` branch / Merge dev to main (backend changes) |
| **frontend-deploy.yml** | `deploy-frontend.sh` | Push to `dev` branch (frontend changes) / Merge dev to main |
| **terraform-bootstrap.yml** | `bootstrap.sh` | Manual workflow dispatch |
| **terraform-deploy.yml** | `terraform-deploy.sh` | Push to `dev`/`main` (terraform changes) + Manual |
| **terraform-pr.yml** | `terraform-validate.sh` | Pull Request (terraform changes) |
| **ecs-manage.yml** | `ecs-control.sh` | Manual workflow dispatch |
| **update-knowledge-base.yml** | `update-knowledge-base.sh` | Push to `dev` branch (docs changes) / Merge dev to main|

---

## Tips

**Save time with aliases:**
```bash
# Add to ~/.bashrc or ~/.zshrc

# Backend deployment
alias deploy-backend-dev="./scripts/build-and-push-docker.sh dev && ./scripts/deploy-ecs.sh dev"
alias deploy-backend-prod="./scripts/build-and-push-docker.sh prod && ./scripts/deploy-ecs.sh prod"

# Frontend deployment
alias deploy-frontend-dev="./scripts/deploy-frontend.sh dev"
alias deploy-frontend-prod="./scripts/deploy-frontend.sh prod"

# Full stack deployment
alias deploy-all-dev="./scripts/build-and-push-docker.sh dev && ./scripts/deploy-ecs.sh dev && ./scripts/deploy-frontend.sh dev"

# ECS operations
alias ecs-logs="./scripts/ecs-control.sh logs dev"
alias ecs-status="./scripts/ecs-control.sh status dev"
alias ecs-deploy="./scripts/ecs-control.sh deploy dev"

# Knowledge Base
alias update-kb="./scripts/update-knowledge-base.sh dev ./docs"

# Terraform operations
alias tf-validate="./scripts/terraform-validate.sh dev"
alias tf-plan="./scripts/terraform-deploy.sh dev plan"
alias tf-apply="./scripts/terraform-deploy.sh dev apply"
```

**Watch deployment progress:**
```bash
# In one terminal
./scripts/deploy-ecs.sh dev

# In another terminal
watch -n 5 './scripts/ecs-control.sh status dev'
```

**Stream live logs:**
```bash
aws logs tail /ecs/artguard-backend --follow --region ca-central-1
```
