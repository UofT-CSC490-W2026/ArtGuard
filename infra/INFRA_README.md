# ArtGuard Infrastructure Documentation

## Table of Contents

1. [Overview](#overview)
2. [Architecture Diagrams](#architecture-diagrams)
3. [Architecture Decisions](#architecture-decisions)
4. [Security](#security)
5. [Monitoring & Observability](#monitoring-observability)
6. [Cost Management](#cost-management)
7. [Disaster Recovery](#disaster-recovery)
8. [Environment Differences](#environment-differences)
---

## Overview


### Key Technologies

- **Compute**: ECS Fargate (serverless containers)
- **Storage**: S3 (images, frontend, docs needed for the RAG model), DynamoDB (for storing metadata), OpenSearch Serverless (vector embeddings)
- **ML/AI**: Amazon Bedrock (for the RAG model), Modal (for the vision model)
- **Networking**: VPC, ALB, CloudFront CDN, VPC Endpoints
- **Monitoring**: CloudWatch (metrics, logs, dashboards), X-Ray (distributed tracing)
- **IaC**: Terraform with environment-specific configs (dev/prod)

### What Gets Deployed
| Component | Description | Quantity |
|-----------|-------------|----------|
| **VPC** | Multi-AZ network with public/private subnets | 1 VPC, 2-3 AZs (2 dev, 3 prod) |
| **ECS Fargate** | Serverless container cluster and service | 1 cluster, 1 service |
| **ALB** | Application Load Balancer with health checks | 1 load balancer |
| **ECR** | Docker registry for backend images | 1 repository |
| **S3** | Object storage buckets | 4 buckets |
| **DynamoDB** | NoSQL tables | 6 tables |
| **Bedrock** | Knowledge base with OpenSearch | 1 knowledge base |
| **CloudFront** | Global CDN distribution | 1 distribution |
| **VPC Endpoints** | Private AWS service access | 5 endpoints |
| **Secrets Manager** | Encrypted secrets storage | 1 secret |

### Resource Details

**S3 Buckets** (4 total):
- `artguard-frontend-{env}` - Frontend static files (served via CloudFront)
- `artguard-images-raw-{env}` - Raw uploaded images (training + inference)
- `artguard-images-processed-{env}` - Processed images and patches
- `artguard-knowledge-base-{env}` - Bedrock Knowledge Base documents (RAG)

**DynamoDB Tables** (6 total):
- `artguard-users-{env}` - User accounts and authentication
- `artguard-inference-records-{env}` - AI inference requests and results
- `artguard-image-records-{env}` - Image metadata and training data
- `artguard-patch-records-{env}` - Image patch metadata
- `artguard-run-records-{env}` - Training run metadata
- `artguard-config-records-{env}` - Hyperparameter configurations per fold

**Secrets Manager** (1 total):
- `artguard/modal-api-key-{env}` - Modal API key for ML model inference

---

## Architecture Diagrams

### High-Level Architecture
![Infra Architecture Diagram](./readme_images/infra_architecture_diagram.png)

### Network Architecture

```
VPC: 10.0.0.0/16 (ca-central-1)
│
├── Public Subnets (Internet Gateway)
│   ├── 10.0.0.0/24 (ca-central-1a) - ALB, NAT Gateway
│   ├── 10.0.1.0/24 (ca-central-1b) - ALB, NAT Gateway
│   └── 10.0.4.0/24 (ca-central-1c) - ALB, NAT Gateway (prod only)
│
├── Private Subnets (NAT Gateway)
│   ├── 10.0.2.0/24 (ca-central-1a) - ECS Tasks
│   ├── 10.0.3.0/24 (ca-central-1b) - ECS Tasks
│   └── 10.0.5.0/24 (ca-central-1c) - ECS Tasks (prod only)
│
└── VPC Endpoints (PrivateLink)
    ├── S3 (Gateway Endpoint)
    ├── ECR API (Interface)
    ├── ECR DKR (Interface)
    ├── CloudWatch Logs (Interface)
    └── Secrets Manager (Interface)
```

### Security Groups

```
┌─────────────────────────────────────────────────────────────┐
│  ALB Security Group (sg-alb)                                │
│  ┌────────────────────────────────────────────────────┐    │
│  │ Inbound:                                            │    │
│  │  - Port 80 (HTTP) from 0.0.0.0/0                   │    │
│  │  - Port 443 (HTTPS) from 0.0.0.0/0                 │    │
│  │                                                      │    │
│  │ Outbound:                                           │    │
│  │  - All traffic (egress to ECS tasks)               │    │
│  └─────────────────────────────────────────────────────┘    │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  ECS Tasks Security Group (sg-ecs-tasks)                    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Inbound:                                            │    │
│  │  - Port 8000 from sg-alb ONLY                      │    │
│  │                                                      │    │
│  │ Outbound:                                           │    │
│  │  - All traffic (AWS services, Modal API)           │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

___

## Architecture Decisions


### 1. Why we chose to use both AWS Bedrock and Modal

**Bedrock (Claude 3.5 Sonnet)**:
- Native AWS integration (no VPC egress needed)
- RAG support with Knowledge Base
- High accuracy for general forgery detection
- No cold starts
- Cost-effective

**Modal (Custom Model)**:
- Specialized forensic analysis
- Faster inference (~2s vs 3-5s)
- Custom fine tuning
- Ensemble with Bedrock for higher explainability

---

### 2. Why VPC Endpoints Despite Extra Cost?

We enabled VPC endpoints for S3, ECR, CloudWatch, Secrets Manager due to the following reasons:

**Security benefits**:
- **Private connectivity**: No internet exposure for AWS API calls
- **Reduced attack surface**: No NAT gateway for AWS services

**Files**: [terraform/networking.tf](terraform/networking.tf)

---

### 3. Why Auto-Pause Scheduler Only in Dev

- **Cost savings**: $35/mo (10 hours × 30 days)
- **No 24/7 availability needed**
- **Fast resume**: ~2 minutes from cold start
- **Risk acceptable**: Dev outages don't affect users
- **Production environment**: 24/7 availability required. Global users across time zones

**Files**: [terraform/scheduler.tf](terraform/scheduler.tf)

---


### 4. Why Data Pipeline Shares the Backend ECS

The data pipeline code lives in the same Docker image and ECS cluster as the backend API due to the following:

-  **It's a one-off script, not a long-running service** — The data pipeline uploads docs to S3 and triggers Bedrock ingestion, then it's done. A separate ECS service would idle 24/7 costing money for nothing.
-  **Separate ECS services make sense for always-running workloads** with different scaling needs (e.g., an API server vs a queue worker). That's not this case.
- **$0 extra cost** — Reuses the existing ECS task. No additional compute, no additional ALB, no additional auto-scaling config.

**How the pipeline runs**:
- Locally via `python -m src.apps.data_pipeline.upload_training_data`
- Optionally as a FastAPI endpoint on the existing backend

---

### 5. DynamoDB vs RDS: Why we chose to go with DynamoDB

1. **Simple relationships**: Only 2 foreign keys (user_id, image_id)
2. **No complex joins**: All "joins" are 1-to-many lookups (inference→user, patch→image)
3. **Known query patterns**: All queries can be optimized with GSIs
4. **High read/write throughput**: Image analysis generates lots of writes
5. **Serverless scaling**: Handles spiky workloads automatically
6. **Pay-per-request**: Only pay for what we use
7. **Cheaper**: Massive cost savings

---

## Security

### 1. Network Security

#### VPC Isolation

- **Private subnets**: ECS tasks have no public IPs
- **Security groups**: Least-privilege ingress/egress rules
- **NAT Gateway**: Controlled internet access for tasks
- **VPC endpoints**: Private AWS service access (no internet)

#### Security Group Rules

**ALB Security Group**:
```hcl
Inbound:
  - Port 80/443 from 0.0.0.0/0 (public API)

Outbound:
  - Port 8000 to ECS tasks security group (application traffic)
```

**ECS Tasks Security Group**:
```hcl
Inbound:
  - Port 8000 from ALB security group ONLY

Outbound:
  - All traffic (AWS services, Modal API)
```

---

### 2. IAM Security

#### IAM Roles

| Role | Purpose | Assumed By |
|------|---------|------------|
| **ECS Execution Role** | Pull ECR images, retrieve secrets from Secrets Manager | `ecs-tasks.amazonaws.com` |
| **ECS Task Role** | Runtime permissions for the application (S3, DynamoDB, Bedrock, CloudWatch) | `ecs-tasks.amazonaws.com` |
| **Bedrock KB Role** | Knowledge Base access to S3, OpenSearch, and embedding model | `bedrock.amazonaws.com` |

#### Least-Privilege Policies

**ECS Execution Role** (infrastructure permissions):
- AWS managed `AmazonECSTaskExecutionRolePolicy` (ECR pull, CloudWatch logs)
- Inline policy: `secretsmanager:GetSecretValue` on Modal API key secret only

**ECS Task Role** (runtime permissions):
```json
{
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan",
        "dynamodb:BatchGetItem",
        "dynamodb:BatchWriteItem"
      ],
      "Resource": ["<all 6 table ARNs>", "<all 6 table ARNs>/index/*"]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
      "Resource": [
        "<images-raw bucket ARN>", "<images-raw bucket ARN>/*",
        "<images-processed bucket ARN>", "<images-processed bucket ARN>/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["bedrock:Retrieve", "bedrock:RetrieveAndGenerate"],
      "Resource": "<knowledge-base ARN>"
    },
    {
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "<ecs-log-group ARN>:*"
    }
  ]
}
```

**Conditional policies** (attached to ECS Task Role):
- **X-Ray** (`enable_xray_tracing = true`): `xray:PutTraceSegments`, `xray:PutTelemetryRecords`, `xray:GetSamplingRules`, `xray:GetSamplingTargets`, `xray:GetSamplingStatisticSummaries`
- **ECS Exec** (`environment == "dev"` only): `ssmmessages:CreateControlChannel`, `ssmmessages:CreateDataChannel`, `ssmmessages:OpenControlChannel`, `ssmmessages:OpenDataChannel`

**Bedrock Knowledge Base Role**:
- S3: `s3:GetObject`, `s3:ListBucket` on knowledge base bucket only
- OpenSearch: `aoss:APIAccessAll` on knowledge base collection only
- Bedrock: `bedrock:InvokeModel` on `amazon.titan-embed-text-v1` model only

**Files**: [terraform/iam.tf](terraform/iam.tf)

---

#### Resource-Based Policies

**Secrets Manager Secret**:
Access is controlled via IAM role policy. The ECS Execution Role has an inline policy that grants `secretsmanager:GetSecretValue` on the Modal API key secret only:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": ["<modal-api-key-secret-arn>*"]
    }
  ]
}
```

**Files**: [terraform/secrets.tf](terraform/secrets.tf), [terraform/iam.tf](terraform/iam.tf)

---

### 3. Data Security

#### Encryption at Rest

- **S3**: AES-256 (SSE-S3) on all buckets
- **DynamoDB**: AWS-managed CMK
- **Secrets Manager**: AWS-managed KMS key
- **OpenSearch**: AWS-managed key

#### Encryption in Transit

- **CloudFront**: TLS 1.2+ enforced
- **ALB → ECS**: HTTP within VPC (private network)
- **ECS → AWS services**: HTTPS via AWS SDK
- **ECS → Modal**: HTTPS required

---

### 4. Secrets Management

#### Current Implementation

**Modal API Key**:
- Stored in Secrets Manager (encrypted)
- Injected as environment variable into ECS tasks

---

## Monitoring & Observability

### 1. CloudWatch Logs

**ECS Tasks**:
- **Log group**: `/ecs/artguard-backend`
- **Retention**: 7 days (dev), 30 days (prod)
- **Contents**: Application logs, errors, request traces


### 2. X-Ray Distributed Tracing

**Status**: Disabled (dev), Enabled (prod)

**Configuration**: Controlled via `var.enable_xray_tracing` in [variables.tf](terraform/variables.tf)

**Benefits**:
- Trace requests across ECS → Bedrock → DynamoDB
- Identify slow API calls
- Visualize service dependencies

**Files**: [terraform/variables.tf](terraform/variables.tf)

---

### 3. Container Insights

**Status**: Enabled in both environments (`enable_container_insights = true`)

**Metrics collected**:
- Container CPU/memory at task level
- Network I/O (bytes sent/received)
- Storage I/O (ephemeral disk)
- Task restart count

**Files**: [terraform/app.tf](terraform/app.tf)

---

### 4. CloudWatch Dashboards

**Dashboard name**: `artguard-dashboard`

**Widgets included**:

1. **ECS - CPU & Memory**
   - CPU Utilization (average)
   - Memory Utilization (average)
   - 5-minute intervals
   - Dimensions: Cluster name, Service name

2. **ALB - Request & Success Metrics**
   - Total request count (sum)
   - 2xx successful responses (sum)
   - 5-minute intervals
   - Dimensions: Load balancer

3. **ALB - Error Metrics**
   - 4xx client errors (sum)
   - 5xx server errors (sum)
   - 5-minute intervals
   - Dimensions: Load balancer

4. **DynamoDB - Consumed Capacity**
   - Read capacity units consumed (sum, all tables)
   - Write capacity units consumed (sum, all tables)
   - Tracks on-demand usage across all 6 tables
   - 5-minute intervals

5. **S3 - Bucket Size**
   - Bucket size in bytes (average)
   - Daily intervals (86400 seconds)
   - Note: S3 bucket metrics are configured for all 4 buckets (frontend, images_raw, images_processed, knowledge_base)

**Files**: [terraform/monitoring.tf](terraform/monitoring.tf)


---

## Cost Management

### Implemented Cost Optimizations

#### 1. Dev Auto-Pause Scheduler

ECS service scales to 0 tasks at 10 PM EST, resumes at 8 AM EST (dev only). Saves ~14 hours/day of compute costs.

**Files**: [terraform/scheduler.tf](terraform/scheduler.tf)

---

#### 2. DynamoDB On-Demand Billing

All 6 tables use `PAY_PER_REQUEST` billing. No wasted provisioned capacity during low usage. Only pay for actual reads/writes.

**Files**: [terraform/database.tf](terraform/database.tf)

---

#### 3. S3 Lifecycle Policies

- `images-raw/training/` — Standard-IA at 30 days (dev) / 90 days (prod) → Glacier at 180 days (no expiration)
- `images-raw/inference/` — Auto-deletes after 7 days (dev) / 30 days (prod)
- `images-processed/` — Standard-IA at 90 days → Glacier at 180 days (no expiration)

Savings: ~60% cheaper in Glacier vs Standard for archived training data.

**Files**: [terraform/s3.tf](terraform/s3.tf)

---

#### 4. CloudWatch Log Retention

Retention set to 7 days (dev), 30 days (prod) instead of indefinite retention.

**Files**: [terraform/app.tf](terraform/app.tf)

---

#### 5. S3 Gateway Endpoint (Free)

S3 traffic from private subnets uses the free Gateway Endpoint instead of going through NAT Gateway, avoiding data transfer charges.

**Files**: [terraform/networking.tf](terraform/networking.tf)

---

## Disaster Recovery

We followed an IaaC approach and used terraform to provision AWS resources for our infrastructure. In the case of an infrastructure failure, running `terraform apply` along with running a couple of scripts to repopulate data within the S3 buckets and dynamo DB tables can help us restore to a functional state.

Here's a video demo where we simulate an infrasture failure by deleting all our resources and then recreate them using terraform: [ADD VIDEO LINK]

## Environment Differences

### Dev vs Prod Configuration

| Setting | Dev | Prod | Rationale |
|---------|-----|------|-----------|
| **ECS Tasks** | 1-5 | 2-10 | Prod needs higher capacity for traffic. Auto-scaling based on CPU/memory/requests. |
| **Task CPU** | 1 vCPU | 2 vCPU | Prod tasks handle more concurrent requests. 1024 vs 2048 CPU units. |
| **Task Memory** | 2 GB | 4 GB | Prod tasks cache more in memory. Sufficient for FastAPI + Bedrock SDK. |
| **Min Capacity** | 1 | 2 | Prod maintains 2 tasks for zero-downtime deploys |
| **Auto-Pause** | Enabled (AppAutoScaling) |  Disabled | Dev doesn't need 24/7 availability |
| **Fargate Spot** | Disabled |  Disabled | Disabled in both environments |
| **VPC Endpoints** | Enabled | Enabled | Security over cost in both environments |
| **NAT Gateways** | 2 | 3 | One per AZ (2 AZs dev, 3 AZs prod) |
| **DynamoDB PITR** | Disabled | Enabled | Hardcoded to `var.environment == "prod"` in database.tf |
| **Log Retention** | 7 days | 30 days | Prod keeps logs longer for audits |
| **Container Insights** | Enabled | Enabled | Enabled in both environments |
| **X-Ray Tracing** |  Disabled | Enabled | Prod has tracing enabled |
| **CloudTrail** |  Disabled |  Recommended | Prod should have audit logs |
| **ACM Certificate** |  None (HTTP) | HTTPS | Prod requires encryption |

| Metric | Dev | Prod | Notes |
|--------|-----|------|-------|
| **Max RPS** | ~50 | ~200 | Assuming 5s avg response time |
| **Cold start** | ~60s | ~30s | Time from 0 tasks to healthy |
