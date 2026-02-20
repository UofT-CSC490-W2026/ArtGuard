# ArtGuard Infrastructure Documentation

## Table of Contents

1. [Overview](#overview)
2. [Architecture Diagrams](#architecture-diagrams)
3. [Architecture Decisions](#architecture-decisions)
4. [Performance & Scalability](#performance--scalability)
5. [Security](#security)
6. [Monitoring & Observability](#monitoring--observability)
7. [Cost Management](#cost-management)
8. [Deployment & Operations](#deployment--operations)
9. [Environment Differences](#environment-differences)

---

## Overview


### Key Technologies

- **Compute**: ECS Fargate (serverless containers)
- **Storage**: S3 (images, frontend), DynamoDB (metadata), OpenSearch Serverless (vector embeddings)
- **ML/AI**: Amazon Bedrock, Modal (vision model)
- **Networking**: VPC, ALB, CloudFront CDN, VPC Endpoints
- **Monitoring**: CloudWatch (metrics, logs, dashboards), X-Ray (distributed tracing)
- **IaC**: Terraform with environment-specific configs (dev/prod)

### What Gets Deployed

Your infrastructure deployment creates:

| Component | Description | Quantity |
|-----------|-------------|----------|
| **VPC** | Multi-AZ network with public/private subnets | 1 VPC, 2 AZs |
| **ECS Fargate** | Serverless container cluster and service | 1 cluster, 1 service |
| **ALB** | Application Load Balancer with health checks | 1 load balancer |
| **ECR** | Docker registry for backend images | 1 repository |
| **S3** | Object storage buckets | 4 buckets |
| **DynamoDB** | NoSQL tables | 6 tables |
| **Bedrock** | Knowledge base with OpenSearch | 1 knowledge base |
| **CloudFront** | Global CDN distribution | 1 distribution |
| **VPC Endpoints** | Private AWS service access | 5 endpoints |
| **Secrets Manager** | Encrypted secrets storage | 1 secret |

---

## Architecture Diagrams

### High-Level Architecture

ADD IMAGE HERE 

### Network Architecture

```
VPC: 10.0.0.0/16 (ca-central-1)
│
├── Public Subnets (Internet Gateway)
│   ├── 10.0.0.0/24 (ca-central-1a) - ALB, NAT Gateway
│   └── 10.0.1.0/24 (ca-central-1b) - ALB, NAT Gateway
│
├── Private Subnets (NAT Gateway)
│   ├── 10.0.2.0/24 (ca-central-1a) - ECS Tasks
│   └── 10.0.3.0/24 (ca-central-1b) - ECS Tasks
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


See [COMPONENT_DESCRIPTION.md](COMPONENT_DESCRIPTION.md) 

___

## Architecture Decisions


### 1. Why Bedrock + Modal?

**Decision**: Support both Bedrock and Modal

**Rationale**:

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

### 2. Why DynamoDB On-Demand vs Provisioned?

**Decision**: Use on-demand billing mode

**Rationale**:
- **Unpredictable traffic**: Can't forecast request patterns in early stages. Too unpredicatable for now.
- **Cost savings**: No wasted capacity during low usage
- **No throttling**: Automatic scaling to any load
- **Simplicity**: No capacity planning, no auto-scaling alarms

**Files**: [infra/terraform/database.tf:20](infra/terraform/database.tf#L20)

---

### 5. Why VPC Endpoints Despite Extra Cost?

**Decision**: Enable VPC endpoints for S3, ECR, CloudWatch, Secrets Manager

**Rationale**:

**Security benefits**:
- **Private connectivity**: No internet exposure for AWS API calls
- **Reduced attack surface**: No NAT gateway for AWS services


**Files**: [infra/terraform/networking.tf:180-280](infra/terraform/networking.tf#L180-L280)

---

### 6. Why Auto-Pause Scheduler Only in Dev?

**Decision**: AppAutoScaling scheduled actions only created for `environment == "dev"`

**Rationale**:

- **Cost savings**: $35/mo (10 hours × 30 days)
- **No 24/7 availability needed**
- **Fast resume**: ~2 minutes from cold start
- **Risk acceptable**: Dev outages don't affect users
- **Production environment**: 24/7 availability required. Global users across time zones

**Manual pause/resume**: Available via GitHub Actions (`ecs-manage.yml`) or AWS CLI

**Files**: [infra/terraform/scheduler.tf](infra/terraform/scheduler.tf)

---


### 7. Why Data Pipeline Shares the Backend ECS

**Decision**: The data pipeline code lives in the same Docker image and ECS cluster as the backend API.

**Rationale**:
-  **It's a one-off script, not a long-running service** — The data pipeline uploads docs to S3 and triggers Bedrock ingestion, then it's done. A separate ECS service would idle 24/7 costing money for nothing.
-  **Separate ECS services make sense for always-running workloads** with different scaling needs (e.g., an API server vs a queue worker). That's not this case.
- **$0 extra cost** — Reuses the existing ECS task. No additional compute, no additional ALB, no additional auto-scaling config.

**How the pipeline runs**:
- Locally via `python -m src.apps.data_pipeline.upload_training_data`
- Via GitHub Actions when docs change in the repo
- Optionally as a FastAPI endpoint on the existing backend

---

### 8. DynamoDB vs RDS for Your Use Case

#### Why DynamoDB Works for You

1. **Simple relationships**: Only 2 foreign keys (user_id, image_id)
2. **No complex joins**: All "joins" are 1-to-many lookups (inference→user, patch→image)
3. **Known query patterns**: All queries can be optimized with GSIs
4. **High read/write throughput**: Image analysis generates lots of writes
5. **Serverless scaling**: Handles spiky workloads automatically
6. **Pay-per-request**: Only pay for what you use
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

**Files**: [infra/terraform/iam.tf](infra/terraform/iam.tf)

---

#### Resource-Based Policies

**Secrets Manager Secret**:
```json
{
  "Statement": [
    {
      "Sid": "AllowECSExecutionAccess",
      "Effect": "Allow",
      "Principal": {"AWS": "<ecs-execution-role-arn>"},
      "Action": ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    },
    {
      "Sid": "AllowAccountRootAccess",
      "Effect": "Allow",
      "Principal": {"AWS": "<account-root-arn>"},
      "Action": "secretsmanager:*"
    },
    {
      "Sid": "DenyAllOthersGetValue",
      "Effect": "Deny",
      "NotPrincipal": {"AWS": ["<ecs-execution-role-arn>", "<account-root-arn>"]},
      "Action": "secretsmanager:GetSecretValue"
    }
  ]
}
```

**Files**: [infra/terraform/secrets.tf:27-68](infra/terraform/secrets.tf#L27-L68)

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

**Access control**:
- Only ECS Execution Role can read
- Resource-based policy denies all other principals
- AWS root account can rotate (for disaster recovery)

**Files**: [infra/disaster_recovery/secret_recovery.sh](infra/disaster_recovery/secret_recovery.sh)


---

## Monitoring & Observability

### 1. CloudWatch Logs

**ECS Tasks**:
- **Log group**: `/ecs/artguard-backend-{env}`
- **Retention**: 7 days (dev), 30 days (prod)
- **Contents**: Application logs, errors, request traces


### 2. X-Ray Distributed Tracing

**Status**: Disabled (dev), Enabled (prod)

**Configuration**: Controlled via `var.enable_xray_tracing` in [variables.tf](infra/terraform/variables.tf)

**Benefits**:
- Trace requests across ECS → Bedrock → DynamoDB
- Identify slow API calls
- Visualize service dependencies

**Files**: [infra/terraform/variables.tf:280](infra/terraform/variables.tf#L280)

---

### 3. Container Insights

**Status**: Enabled in both environments (`enable_container_insights = true`)

**Metrics collected**:
- Container CPU/memory at task level
- Network I/O (bytes sent/received)
- Storage I/O (ephemeral disk)
- Task restart count

**Files**: [infra/terraform/app.tf:15-17](infra/terraform/app.tf#L15-L17)

---

### 4. CloudWatch Dashboards

**Dashboard name**: `artguard-dashboard`

**Widgets included**:

1. **ECS - CPU & Memory**
   - CPU Utilization (average)
   - Memory Utilization (average)
   - 5-minute intervals

2. **ALB - Request Metrics**
   - Total request count
   - 2xx successful responses
   - 4xx client errors
   - 5xx server errors
   - 5-minute intervals

3. **DynamoDB - Consumed Capacity**
   - Read capacity units consumed
   - Write capacity units consumed
   - Tracks on-demand usage
   - 5-minute intervals

4. **S3 - Bucket Size**
   - Images raw bucket size
   - Images processed bucket size
   - Daily intervals

**Files**: [infra/terraform/monitoring.tf:3-90](infra/terraform/monitoring.tf#L3-L90)


---

### Implemented Cost Optimizations

#### 1. Dev Auto-Pause Scheduler

ECS service scales to 0 tasks at 10 PM EST, resumes at 8 AM EST (dev only). Saves ~14 hours/day of compute costs.

**Files**: [infra/terraform/scheduler.tf](infra/terraform/scheduler.tf)

---

#### 2. DynamoDB On-Demand Billing

All 6 tables use `PAY_PER_REQUEST` billing. No wasted provisioned capacity during low usage. Only pay for actual reads/writes.

**Files**: [infra/terraform/database.tf](infra/terraform/database.tf)

---

#### 3. S3 Lifecycle Policies

- `images-raw/training/` — Standard-IA at 30 days (dev) / 90 days (prod) → Glacier at 180 days (no expiration)
- `images-raw/inference/` — Auto-deletes after 7 days (dev) / 30 days (prod)
- `images-processed/` — Standard-IA at 90 days → Glacier at 180 days (no expiration)

Savings: ~60% cheaper in Glacier vs Standard for archived training data.

**Files**: [infra/terraform/s3.tf](infra/terraform/s3.tf)

---

#### 4. CloudWatch Log Retention

Retention set to 7 days (dev), 30 days (prod) instead of indefinite retention.

**Files**: [infra/terraform/app.tf:204-207](infra/terraform/app.tf#L204-L207)

---

#### 5. S3 Gateway Endpoint (Free)

S3 traffic from private subnets uses the free Gateway Endpoint instead of going through NAT Gateway, avoiding data transfer charges.

**Files**: [infra/terraform/networking.tf:130-137](infra/terraform/networking.tf#L130-L137)

---

#### 6. CloudFront PriceClass_100

Restricts edge locations to North America and Europe only (cheapest tier) instead of global distribution.

**Files**: [infra/terraform/cloudfront.tf](infra/terraform/cloudfront.tf)

---

### Disaster Recovery

TO DO 

#### Backup Strategy

TO DO 

---

#### Recovery Procedures
(IDK IF THIS IS USEFUL, KEEP OR DELETE)

**Scenario 1: ECS service down**:
```bash
# Check service status
aws ecs describe-services \
  --cluster artguard-cluster-prod \
  --services artguard-backend-prod

# Force new deployment (rolling restart)
aws ecs update-service \
  --cluster artguard-cluster-prod \
  --service artguard-backend-prod \
  --force-new-deployment

# If still failing, scale to 0 then back to min capacity
aws ecs update-service --desired-count 0 ...
aws ecs update-service --desired-count 2 ...
```

---

**Scenario 2: Terraform state corrupted**:
```bash
# List available state versions
aws s3api list-object-versions \
  --bucket artguard-terraform-state \
  --prefix env/prod/terraform.tfstate

# Download specific version
aws s3api get-object \
  --bucket artguard-terraform-state \
  --key env/prod/terraform.tfstate \
  --version-id <version-id> \
  terraform.tfstate.backup

# Restore to S3
aws s3 cp terraform.tfstate.backup \
  s3://artguard-terraform-state/env/prod/terraform.tfstate
```

---

**Scenario 3: DynamoDB table accidentally deleted**:
```bash
# Restore from point-in-time recovery (within 35 days)
aws dynamodb restore-table-to-point-in-time \
  --source-table-name artguard-inference-records-prod \
  --target-table-name artguard-inference-records-prod-restored \
  --restore-date-time 2024-02-07T10:00:00Z

# Or restore from on-demand backup
aws dynamodb restore-table-from-backup \
  --target-table-name artguard-inference-records-prod-restored \
  --backup-arn arn:aws:dynamodb:ca-central-1:...:backup/...
```

---

**Scenario 4: Modal API key leaked**:
```bash
# Rotate immediately
# 1. Generate new key in Modal dashboard
# 2. Update Secrets Manager
aws secretsmanager put-secret-value \
  --secret-id artguard/modal-api-key-prod \
  --secret-string '{"api_key":"modal-NEW-KEY-HERE"}'

# 3. Force ECS service restart (picks up new secret)
aws ecs update-service \
  --cluster artguard-cluster-prod \
  --service artguard-backend-prod \
  --force-new-deployment

# 4. Revoke old key in Modal dashboard
```

**Files**: [infra/disaster_recovery/secret_recovery.sh](infra/disaster_recovery/secret_recovery.sh)

---

## Environment Differences

TO DO 


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


**Files**: [infra/terraform/dev.tfvars](infra/terraform/dev.tfvars), [infra/terraform/prod.tfvars](infra/terraform/prod.tfvars)
