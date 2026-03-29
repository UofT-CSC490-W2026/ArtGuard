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
# Upload RAG data (Met Museum + Wikidata) to Bedrock Knowledge Base
./scripts/upload-rag-data.sh
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

### **Benchmarking (Model Training & Evaluation)**
```bash
# Train + evaluate Swin-Tiny (default)
./scripts/run-benchmarks.sh tiny

# Evaluate only (uses existing checkpoint on Modal Volume)
./scripts/run-benchmarks.sh tiny eval

# Train only (skip evaluation)
./scripts/run-benchmarks.sh tiny train

# Both variants (Swin-Tiny + Swin-Base)
./scripts/run-benchmarks.sh
```

---

## Detailed Documentation

### Entry Point Scripts (run these directly)

These are the main scripts you invoke from the command line or CI. They orchestrate the full workflow.

| Script | Purpose | Used by CI |
|--------|---------|------------|
| **deploy-all.sh** | Full end-to-end deployment (7 steps: infra + secrets + Docker + ECS + RAG + data + verify) | No (manual) |
| **destroy-all.sh** | Tear down infrastructure (full wipe or `--preserve-data` for DR) | `terraform-destroy.yml` |
| **disaster-recovery.sh** | One-command DR demo (destroy + prove data survived + recover) | No (manual demo) |
| **deploy-frontend.sh** | Build Vite React app and deploy to S3/CloudFront | `frontend-deploy.yml` |
| **ecs-control.sh** | Manual ECS service operations (deploy, scale, status, logs) | `ecs-manage.yml` |
| **terraform-validate.sh** | Validate Terraform config and create plan (for PRs) | `terraform-pr.yml` |
| **run-benchmarks.sh** | Train and/or evaluate Swin models on Modal GPUs | No (manual) |
| **demo-rag-bugs.sh** | Interactive video demo of RAG deployment bugs and fixes | No (manual demo) |
| **download-data.sh** | Download training/test/val images from Google Drive | No (manual) |

### Building Block Scripts (called by other scripts)

These scripts are designed to do one thing well. They are called by the entry point scripts above and by CI workflows, but can also be run standalone.

| Script | Purpose | Called by |
|--------|---------|----------|
| **bootstrap.sh** | One-time Terraform infrastructure setup | `deploy-all.sh`, `terraform-bootstrap.yml` |
| **build-and-push-docker.sh** | Build Docker image and push to ECR | `deploy-all.sh`, `recover-prod.sh`, `app-docker.yml` |
| **deploy-ecs.sh** | Force ECS rolling deployment | `deploy-all.sh`, `recover-prod.sh`, `app-docker.yml` |
| **setup-secrets.sh** | Upload Modal API key to Secrets Manager | `deploy-all.sh`, `recover-prod.sh` |
| **terraform-deploy.sh** | Terraform init/plan/apply/destroy wrapper | `terraform-validate.sh`, `terraform-deploy.yml` |
| **upload-rag-data.sh** | Convert JSONL to TXT and sync to S3 for Bedrock KB | `deploy-all.sh` |
| **update-data.sh** | Upload local images + metadata to S3 and DynamoDB | `deploy-all.sh` |
| **recover-prod.sh** | 10-step disaster recovery automation | `disaster-recovery.sh` |

### Shared Utilities

| Script | Purpose |
|--------|---------|
| **_colors.sh** | Color definitions and output helpers (`info`, `success`, `warn`, `error`, `step`, `header`, `require_tool`). Sourced by all other scripts. |

---

## Data & Git LFS

Training, test, and validation images (`data/`) are **not stored in the Git repo** — they are too large (~2.1 GB) for Git or Git LFS free tier.

**What's included in the repo (cloned automatically):**
- `src/apps/data_pipeline/output/` — RAG knowledge base text/jsonl
- All source code, Terraform configs, scripts, etc.

**What's NOT in the repo (must be downloaded separately):**
- `data/train/` — training images (class_0 = forgery, class_1 = authentic)
- `data/test/` — test images
- `data/val/` — validation images

### Downloading the dataset

```bash
./scripts/download-data.sh
```

This downloads a zip from Google Drive and extracts it to `data/`. Requires `gdown` (`pip install gdown`).

> **Note:** The deployed application works without `data/` — training images are already in S3 and model weights are on Modal. The download is only needed for local training/evaluation or dataset inspection. Google drive link: https://drive.google.com/file/d/1-MJgGpVtHQ1FDDy5Cy7puf2pmErSTFJZ/view?usp=drive_link

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
Builds the **Vite** SPA (`npm run build` → `dist/`) and deploys to S3 + CloudFront.

**Usage:**
```bash
export VITE_API_URL="https://YOUR_CLOUDFRONT_OR_API_BASE"   # required, no trailing slash
./scripts/deploy-frontend.sh [environment]
```

**Environment Variables:**
- **`VITE_API_URL`** (required) — Public API base URL compiled into the bundle (e.g. `https://dxxxx.cloudfront.net/api` if the API is under `/api/*` on CloudFront).
- `AWS_REGION` — S3 sync region (default: `ca-central-1`)

**What it does:**
1. Cleans previous `dist/` output
2. Installs npm dependencies with `npm ci`
3. Builds Vite production bundle
4. Syncs static assets to S3 with long cache (31536000s)
5. Syncs HTML/JSON with short cache (0s, must-revalidate)
6. Invalidates CloudFront cache for immediate updates
7. Takes ~5-10 minutes total

**Examples:**
```bash
export VITE_API_URL="https://d1b5yxlog377uv.cloudfront.net/api"
./scripts/deploy-frontend.sh dev

export VITE_API_URL="https://d1b5yxlog377uv.cloudfront.net/api"
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

### **upload-rag-data.sh**
Converts pipeline JSONL output to chunked TXT files and uploads them to the Bedrock Knowledge Base S3 bucket, then triggers an ingestion job.

**Usage:**
```bash
./scripts/upload-rag-data.sh
```

**What it does:**
1. Reads Terraform outputs to get the KB bucket name, Knowledge Base ID, and data source ID
2. Runs `scripts/convert-jsonl-to-txt.py` to convert `src/apps/data_pipeline/output/*.jsonl` into chunked TXT files (max 500 records per file)
3. Syncs TXT files to S3 (`artguard-knowledge-base-{env}`)
4. Triggers a Bedrock Knowledge Base ingestion job
5. Waits for ingestion to complete (~10-20 minutes)

**Examples:**
```bash
./scripts/upload-rag-data.sh
```

**Output:**
- S3 Bucket: `artguard-knowledge-base-{environment}`
- Source: `src/apps/data_pipeline/output/txt/*.txt` (Met Museum + Wikidata)
- Ingestion: Bedrock creates vector embeddings in OpenSearch Serverless

---

## GitHub Actions Integration

All scripts are designed to work both locally and in GitHub Actions:

| Workflow | Scripts Used | Trigger |
|----------|-------------|---------|
| **app-docker.yml** | `build-and-push-docker.sh` + `deploy-ecs.sh` | Push to `dev` branch / Merge dev to main (backend changes) |
| **frontend-deploy.yml** | `deploy-frontend.sh` | Push to `dev` branch (frontend changes) / Merge dev to main |
| **terraform-bootstrap.yml** | `bootstrap.sh` | Manual workflow dispatch |
| **terraform-deploy.yml** | `terraform-deploy.sh` | Push to `dev`/`main` (terraform changes) + Manual |
| **terraform-destroy.yml** | `destroy-all.sh` | Manual workflow dispatch (double confirmation) |
| **terraform-pr.yml** | `terraform-validate.sh` | Pull Request (terraform changes) |
| **ecs-manage.yml** | `ecs-control.sh` | Manual workflow dispatch |
| **test-coverage.yml** | pytest + pytest-cov | Push to main / Pull Request |
| **secret.yml** | (inline) | Manual workflow dispatch (DR secret injection) |

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
alias update-kb="./scripts/upload-rag-data.sh"

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
