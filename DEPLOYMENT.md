# ArtGuard Deployment Guide

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [First-Time Setup](#first-time-setup)
3. [Initial Deployment](#initial-deployment)
4. [Ongoing Development Workflow](#ongoing-development-workflow)
5. [GitHub Actions Integration](#github-actions-integration)
6. [Manual Operations](#manual-operations)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Accounts & Tools

- **AWS Account** 
- **Modal Account** with API key for AI model inference
- **GitHub Account** with repository access
- **Local Tools:**
  - AWS CLI (`brew install awscli` or https://aws.amazon.com/cli/)
  - Terraform (`brew install terraform` or https://terraform.io)
  - Docker Desktop (https://docker.com/products/docker-desktop)
  - Node.js 18+ (`brew install node`)
  - Python 3.9+ (`brew install python`)

### AWS Credentials Setup

Choose one method:

```bash
# Option 1: AWS CLI Configuration (Recommended)
aws configure
# Enter: Access Key ID, Secret Access Key, Region (ca-central-1), Output format (json)

# Option 2: Environment Variables
export AWS_ACCESS_KEY_ID="your-access-key-id"
export AWS_SECRET_ACCESS_KEY="your-secret-access-key"
export AWS_REGION="ca-central-1"

# Option 3: AWS Profile
export AWS_PROFILE="your-profile-name"
```

**Verify AWS access:**
```bash
aws sts get-caller-identity
```
---

## First-Time Setup

This is a **ONE-TIME** process to create all infrastructure from scratch. Read about the scripts at [scripts/README.md](#scripts/README.md)

### Step 1: Clone Repository

```bash
git clone https://github.com/UofT-CSC490-W2026/ArtGuard.git
cd ArtGuard
```

### Step 2: Make Scripts Executable

```bash
chmod +x scripts/*.sh
```

### Step 3: Bootstrap Infrastructure

This creates all AWS resources (VPC, ECS, ALB, S3, DynamoDB, etc.)

```bash
# For dev environment
./scripts/bootstrap.sh dev

# For prod environment
./scripts/bootstrap.sh prod
```

**What bootstrap.sh does:**
1. Creates S3 bucket for Terraform state (`artguard-terraform-state`)
2. Creates DynamoDB table for state locking (`artguard-terraform-locks`)
3. Initializes Terraform backend
4. Creates all infrastructure:
   
### Step 4: Store Modal API Key

```bash
./scripts/setup-secrets.sh dev
# Enter your Modal API key when prompted
```

**What setup-secrets.sh does:**
- Prompts for Modal API key (hidden input)
- Stores it securely in AWS Secrets Manager
- ECS tasks will retrieve this at runtime

---

## Initial Deployment

After infrastructure exists, deploy your applications.

### Step 5: Build and Push Backend Docker Image

```bash
./scripts/build-and-push-docker.sh dev
```

**Expected duration:** 5-10 minutes (depending on Docker build)

### Step 6: Deploy to ECS Fargate

```bash
./scripts/deploy-ecs.sh dev
```

**Expected duration:** 3-5 minutes

**Verify deployment:**
```bash
./scripts/ecs-control.sh status dev
```

### Step 7: Deploy Lambda Functions

```bash
./scripts/deploy-lambda.sh dev
```

**Expected duration:** 2-3 minutes

### Step 8: Deploy Frontend

```bash
./scripts/deploy-frontend.sh dev
```

**Expected duration:** 5-10 minutes

### Step 9: (Optional) Update Knowledge Base

If you have documentation for RAG:

```bash
./scripts/update-knowledge-base.sh dev ./docs
```

**Expected duration:** 2-10 minutes depending on document count

---

## Ongoing Development Workflow

After initial setup, this is your daily workflow.

1. Develop and test on `dev` branch → deploys to dev environment
2. Create PR from `dev` → `main` → triggers validation
3. Merge to `main` → deploys to prod environment

---

## GitHub Actions Integration

### Required GitHub Secrets

For GitHub Actions to work, configure these secrets in the repository:

**Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | Value | Purpose |
|------------|-------|---------|
| `AWS_ACCESS_KEY_ID` | Your AWS access key | Authenticate GitHub Actions to AWS |
| `AWS_SECRET_ACCESS_KEY` | Your AWS secret key | Authenticate GitHub Actions to AWS |
| `AWS_REGION` | `ca-central-1` | AWS region (optional, defaults in workflows) |

**How to create AWS credentials for GitHub:**

```bash
# Create IAM user for CI/CD
aws iam create-user --user-name github-actions-artguard

# Attach necessary policies
aws iam attach-user-policy \
  --user-name github-actions-artguard \
  --policy-arn arn:aws:iam::aws:policy/PowerUserAccess

# Create access key
aws iam create-access-key --user-name github-actions-artguard
# Save the AccessKeyId and SecretAccessKey output
```

## 🔄 Complete Deployment Workflow

### Workflow Execution Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Your Development Flow                      │
└─────────────────────────────────────────────────────────────┘

1. Edit Code Locally
   ├── src/apps/backend/        → Triggers app-docker.yml
   ├── src/apps/frontend/       → Triggers frontend-deploy.yml
   ├── infra/terraform/         → Triggers terraform-deploy.yml
   └── docs/                    → Triggers update-knowledge-base.yml

2. Create Pull Request
   └── infra/terraform/ changed → Triggers terraform-pr.yml (validation)

3. Merge to dev/main
   └── Automatic deployments run based on changed files

4. Manual Operations (GitHub UI)
   ├── First time setup          → terraform-bootstrap.yml
   ├── ECS management            → ecs-manage.yml
   ├── Emergency teardown        → terraform-destroy.yml
   └── Secret recovery           → secret.yml

┌─────────────────────────────────────────────────────────────┐
│              Complete Deployment Pipeline                     │
└─────────────────────────────────────────────────────────────┘

Code Change → Git Push → GitHub Actions → AWS Deployment → Live

Example: Backend Update
  1. Edit src/apps/backend/app.py
  2. git push origin dev
  3. app-docker.yml triggers automatically
  4. Builds Docker → Pushes to ECR → Deploys to ECS
  5. New version live in ~15 minutes

Example: Frontend Update
  1. Edit src/apps/frontend/src/App.js
  2. git push origin dev
  3. frontend-deploy.yml triggers automatically
  4. Builds React → Syncs to S3 → Invalidates CloudFront
  5. New version live in ~10 minutes

Example: Infrastructure Update
  1. Edit infra/terraform/ecs.tf (increase task count)
  2. git push origin dev
  3. terraform-deploy.yml triggers automatically
  4. Runs terraform apply → Updates ECS service
  5. Infrastructure updated in ~5 minutes
```


### Quick Reference: When to Use Each Workflow

| I Want To... | Use This Workflow | How | Manual CLI Command |
|--------------|-------------------|-----|-------------------|
| **Deploy backend code changes** | app-docker.yml | Just push to `dev` or `main` - automatic | `./scripts/build-and-push-docker.sh dev && ./scripts/deploy-ecs.sh dev` |
| **Deploy frontend code changes** | frontend-deploy.yml | Just push to `dev` or `main` - automatic | `./scripts/deploy-frontend.sh dev` |
| **Update infrastructure (ECS, S3, etc.)** | terraform-deploy.yml | Edit .tf files, push to `dev`/`main` - automatic | `cd infra/terraform && ./scripts/terraform-deploy.sh dev apply` |
| **Create infrastructure for first time** | terraform-bootstrap.yml | GitHub UI → Actions → Run workflow → Type "BOOTSTRAP" | `./scripts/bootstrap.sh dev` |
| **Force ECS to redeploy latest image** | ecs-manage.yml | GitHub UI → Actions → Select "deploy" action | `./scripts/ecs-control.sh deploy dev` |
| **Scale ECS tasks up/down** | ecs-manage.yml | GitHub UI → Actions → Select "scale" → Enter count | `./scripts/ecs-control.sh scale dev 3` |
| **View ECS service status** | ecs-manage.yml | GitHub UI → Actions → Select "status" | `./scripts/ecs-control.sh status dev` |
| **View ECS logs** | ecs-manage.yml | GitHub UI → Actions → Select "logs" | `./scripts/ecs-control.sh logs dev` |
| **Deploy Lambda function changes** | lambda-deploy.yml | Just push to `dev` or `main` - automatic | `./scripts/deploy-lambda.sh dev` |
| **Update documentation for RAG** | update-knowledge-base.yml | Edit docs/, push to `main` - automatic | `./scripts/update-knowledge-base.sh dev ./docs` |
| **Validate infrastructure changes** | terraform-pr.yml | Create PR with .tf changes - automatic | `./scripts/terraform-validate.sh dev` |
| **Destroy all infrastructure** | terraform-destroy.yml | GitHub UI → Actions → Run workflow → Type "DESTROY" ⚠️ | `cd infra/terraform && ./scripts/terraform-deploy.sh dev destroy` |
| **Restore lost secrets** | secret.yml | GitHub UI → Actions → Run workflow | `MODAL_API_KEY='xxx' ./infra/disaster_recovery/secret_recovery.sh dev` |

---

## CLI Commands 

### ECS Service Management

```bash
# Check ECS service status
./scripts/ecs-control.sh status dev

# Scale ECS service
./scripts/ecs-control.sh scale dev 3

# Force new deployment
./scripts/ecs-control.sh deploy dev

# View recent logs
./scripts/ecs-control.sh logs dev
```


### Direct AWS Operations

```bash
# View ECS tasks
aws ecs list-tasks --cluster artguard-cluster --region ca-central-1

# View CloudWatch logs
aws logs tail /ecs/artguard-backend --follow --region ca-central-1

# View S3 buckets
aws s3 ls | grep artguard

# View ECR images
aws ecr describe-images --repository-name artguard-backend --region ca-central-1
```

---

## Troubleshooting

### Common Issues

#### 1. Docker Build Fails

**Problem:** `docker build` command fails or times out

**Solution:**
```bash
# Ensure Docker Desktop is running
open -a Docker

# Clean Docker cache
docker system prune -a

# Rebuild
./scripts/build-and-push-docker.sh dev
```

#### 2. ECS Tasks Failing Health Checks

**Problem:** ECS tasks start but fail health checks and get terminated

**Solution:**
```bash
# Check logs
./scripts/ecs-control.sh logs dev

# Common causes:
# - Application not listening on port 8080
# - Application takes too long to start (increase health check grace period)
# - Missing environment variables
# - Modal API key not configured

# Verify Modal API key
aws secretsmanager get-secret-value \
  --secret-id artguard-modal-api-key \
  --region ca-central-1
```

#### 3. CloudFront Not Serving Updated Content

**Problem:** Frontend changes not visible after deployment

**Solution:**
```bash
# Manual invalidation
aws cloudfront create-invalidation \
  --distribution-id <DISTRIBUTION_ID> \
  --paths "/*" \
  --region us-east-1

# Or redeploy
./scripts/deploy-frontend.sh dev
```

#### 4. GitHub Actions Failing

**Problem:** Workflows fail with authentication errors

**Solution:**
1. Verify GitHub Secrets are configured correctly
2. Check AWS credentials have not expired
3. Verify IAM permissions for GitHub Actions user

```bash
# Test credentials locally
export AWS_ACCESS_KEY_ID="<from-github-secret>"
export AWS_SECRET_ACCESS_KEY="<from-github-secret>"
aws sts get-caller-identity
```

## Viewing Resources

```bash
# ECS Cluster
aws ecs describe-clusters --clusters artguard-cluster --region ca-central-1

# Load Balancer
aws elbv2 describe-load-balancers --region ca-central-1 | grep artguard

# S3 Buckets
aws s3 ls | grep artguard

# CloudFront Distributions
aws cloudfront list-distributions --region us-east-1

# VPC
aws ec2 describe-vpcs --region ca-central-1 | grep artguard

# Lambda Functions
aws lambda list-functions --region ca-central-1 | grep artguard
```

---

## Quick Reference

### Most Common Commands

```bash
# Daily development
git push origin dev                              # Deploy everything automatically

# Manual backend deployment
./scripts/build-and-push-docker.sh dev && ./scripts/deploy-ecs.sh dev

# Manual frontend deployment
./scripts/deploy-frontend.sh dev

# Check status
./scripts/ecs-control.sh status dev

# View logs
./scripts/ecs-control.sh logs dev

# Scale ECS
./scripts/ecs-control.sh scale dev 3        # Scale up
./scripts/ecs-control.sh scale dev 0        # Scale down (cost saving)


# Infrastructure changes
./scripts/terraform-validate.sh dev              # Validate
cd infra/terraform && ./scripts/terraform-deploy.sh dev apply  # Apply
```

### Key URLs (Dev Environment)

After deployment, find your URLs:

```bash
# Backend API
terraform output -state=infra/terraform/terraform.tfstate backend_url

# Frontend URL
terraform output -state=infra/terraform/terraform.tfstate cloudfront_distribution_url

```

### Emergency Commands

```bash
# Stop all services (cost emergency)
./scripts/ecs-control.sh scale dev 0

# Force new deployment
./scripts/ecs-control.sh deploy dev

# Invalidate CloudFront
aws cloudfront create-invalidation \
  --distribution-id $(cd infra/terraform && terraform output -raw cloudfront_distribution_id) \
  --paths "/*" \
  --region us-east-1

# Rollback Docker image
# Find previous image:
aws ecr describe-images --repository-name artguard-backend --region ca-central-1
# Update ECS task definition manually or redeploy previous git commit
```
---

**View CloudWatch Dashboard:**
```bash
# Get dashboard URL
echo "https://console.aws.amazon.com/cloudwatch/home?region=ca-central-1#dashboards:name=artguard-dashboard"
```

```bash
# List images in ECR
aws ecr describe-images \
  --repository-name artguard-backend \
  --region ca-central-1 \
  --query 'sort_by(imageDetails, &imagePushedAt)[-10:]' \
  --output table

# Get latest image tag
aws ecr describe-images \
  --repository-name artguard-backend \
  --region ca-central-1 \
  --query 'sort_by(imageDetails, &imagePushedAt)[-1].imageTags[0]' \
  --output text
```

### Check CloudFront Distribution

```bash
# Get distribution ID
cd infra/terraform
terraform output -raw cloudfront_distribution_id

# Check distribution status
aws cloudfront get-distribution \
  --id $(terraform output -raw cloudfront_distribution_id) \
  --query 'Distribution.Status' \
  --output text
```


**View Logs:**
### ECS Logs (Backend)

```bash
# View last 50 log entries
./scripts/ecs-control.sh logs dev

# Follow logs in real-time
aws logs tail /ecs/artguard-backend \
  --follow \
  --region ca-central-1

# View logs from last hour
aws logs tail /ecs/artguard-backend \
  --since 1h \
  --format short \
  --region ca-central-1

# View logs from specific time
aws logs tail /ecs/artguard-backend \
  --since 2026-02-14T10:00:00 \
  --until 2026-02-14T11:00:00 \
  --region ca-central-1

# Filter logs by keyword
aws logs tail /ecs/artguard-backend \
  --follow \
  --filter-pattern "ERROR" \
  --region ca-central-1

# Save logs to file
aws logs tail /ecs/artguard-backend \
  --since 1h \
  --format short \
  --region ca-central-1 > backend-logs.txt
```

### Lambda Logs

```bash
# View image processor logs
aws logs tail /aws/lambda/artguard-image-processor \
  --follow \
  --region ca-central-1

# View ECS scheduler logs
aws logs tail /aws/lambda/artguard-ecs-scheduler \
  --follow \
  --region ca-central-1

# View recent errors
aws logs tail /aws/lambda/artguard-image-processor \
  --since 1h \
  --filter-pattern "ERROR" \
  --region ca-central-1
```

**Testing:**
```bash

# Get backend URL
BACKEND_URL=$(terraform output -state=infra/terraform/terraform.tfstate.d/dev/terraform.tfstate -raw backend_url)

# Get frontend URL
FRONTEND_URL=$(terraform output -state=infra/terraform/terraform.tfstate.d/dev/terraform.tfstate -raw cloudfront_distribution_url)

# Test frontend
curl https://${FRONTEND_URL}

# Test backend health
curl ${BACKEND_URL}/health

# Upload test image to S3
aws s3 cp test.jpg s3://artguard-images-raw-dev/inference/test.jpg --region ca-central-1
```

---
