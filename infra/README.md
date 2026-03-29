# ArtGuard Infrastructure Documentation

## Table of Contents

1. [Overview](#overview)
2. [Architecture Diagrams](#architecture-diagrams)
3. [Component Breakdown](#component-breakdown)
4. [Architecture Decisions](#architecture-decisions)
5. [Security](#security)
6. [Logging & Structured Metrics](#logging--structured-metrics)
7. [Monitoring & Observability](#monitoring--observability)
8. [Cost Management](#cost-management)
9. [Disaster Recovery](#disaster-recovery)
10. [Environment Differences](#environment-differences)

---

## Overview

### Key Technologies

- **Compute**: ECS Fargate (serverless containers)
- **Storage**: S3 (images, frontend, docs needed for the RAG model), DynamoDB (for storing metadata), OpenSearch Serverless (vector embeddings)
- **ML/AI**: Amazon Bedrock (for the RAG model), Modal (for the vision model)
- **Networking**: VPC, ALB, CloudFront CDN, VPC Endpoints
- **Monitoring**: CloudWatch (metrics, logs, dashboards, alarms), X-Ray (distributed tracing)
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
![Infra Architecture Diagram](./infrastructure_architecture_diagram.png)

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

---

## Component Breakdown

### 1. ECS Fargate (Backend API)

**Purpose**: Runs the Python FastAPI backend in serverless containers

**Configuration**:
- **Cluster**: `artguard-cluster-dev/prod`
- **Service**: `artguard-backend-dev/prod`
- **Task Definition**:
  - Image: ECR `{account}.dkr.ecr.ca-central-1.amazonaws.com/artguard-backend:latest`
  - CPU: 1024 (1 vCPU) in dev, 2048 (2 vCPU) in prod
  - Memory: 2048 MB in dev, 4096 MB in prod
  - Port: 8000 (container) → 8000 (ALB target)
  - Launch type: FARGATE (no EC2 instance management)

**Auto-Scaling**:
- **Target Tracking Policies**:
  - CPU > 70% → scale out
  - Memory > 80% → scale out
  - Request count > 1000 req/task → scale out
- **Capacity**:
  - Dev: 1-5 tasks
  - Prod: 2-10 tasks
- **Cooldown**: 60s scale-out, 300s scale-in

**Health Checks**:
- **ALB Target Group**:
  - Path: `/health`
  - Interval: 30s
  - Timeout: 5s
  - Healthy threshold: 2 consecutive successes
  - Unhealthy threshold: 3 consecutive failures
  - Expected response: HTTP 200

**Networking**:
- Deploys in private subnets (10.0.2.0/24, 10.0.3.0/24)
- Receives traffic from ALB only
- Outbound access via NAT Gateway or VPC endpoints

**Environment Variables** (injected via ECS task definition):
```bash
ENVIRONMENT=dev
AWS_REGION=ca-central-1
S3_IMAGES_RAW_BUCKET=artguard-images-raw-dev
S3_IMAGES_PROCESSED_BUCKET=artguard-images-processed-dev
DDB_USERS_TABLE=artguard-users-dev
DDB_INFERENCES_TABLE=artguard-inference-records-dev
DDB_IMAGES_TABLE=artguard-image-records-dev
DDB_PATCHES_TABLE=artguard-patch-records-dev
DDB_RUNS_TABLE=artguard-run-records-dev
DDB_CONFIGS_TABLE=artguard-config-records-dev
KNOWLEDGE_BASE_ID=<bedrock knowledge base ID>
MODAL_API_KEY=<from Secrets Manager>      # injected via ECS secrets (Execution Role)
JWT_SECRET_KEY=<from Secrets Manager>     # injected via ECS secrets (Execution Role)
```

**Files**: [terraform/app.tf](terraform/app.tf)

---

### 2. Application Load Balancer (ALB)

**Purpose**: Routes HTTPS traffic to ECS tasks, performs health checks

**Configuration**:
- **Type**: Application Load Balancer
- **Scheme**: Internet-facing
- **Subnets**: Public subnets in 2 AZs
- **Security**: TLS 1.2+ only (if HTTPS configured)
- **Idle timeout**: 60 seconds

**Listeners**:
- Port 80 (HTTP) → forwards to port 8000 target group
- Port 443 (HTTPS) → optional, requires ACM certificate

**Target Group**:
- **Protocol**: HTTP
- **Port**: 8000
- **Target type**: IP (Fargate tasks)
- **Deregistration delay**: 30 seconds
- **Stickiness**: None (stateless API)

**CloudWatch Metrics**:
- `RequestCount` - Total requests
- `TargetResponseTime` - Backend latency
- `HTTPCode_Target_2XX_Count` - Successful responses
- `HTTPCode_Target_4XX_Count` - Client errors
- `HTTPCode_Target_5XX_Count` - Server errors
- `HealthyHostCount` / `UnHealthyHostCount` - Task health

**Files**: [terraform/app.tf](terraform/app.tf)

---

### 3. S3 Buckets

#### 3a. Frontend Bucket

**Purpose**: Hosts React application static files

**Configuration**:
- **Name**: `artguard-frontend-{env}`
- **Public access**: Blocked (served via CloudFront only)
- **Encryption**: AES-256 (SSE-S3)
- **Versioning**: Disabled
- **Lifecycle**: None (small static assets)

**Content Structure**:
```
artguard-frontend-dev/
├── index.html
├── static/
│   ├── css/
│   ├── js/
│   └── media/
└── manifest.json
```

**Cache Headers** (set by `deploy-frontend.sh`):
- `.html`, `.json`: `max-age=0, must-revalidate`
- `.js`, `.css`, `.png`, `.jpg`: `max-age=31536000` (1 year)

**Files**: [terraform/s3.tf](terraform/s3.tf)

---

#### 3b. Images Raw Bucket

**Purpose**: Stores user-uploaded images for forgery detection

**Configuration**:
- **Name**: `artguard-images-raw-{env}`
- **Public access**: Blocked
- **Encryption**: AES-256
- **Versioning**: Disabled
- **Lifecycle**:
  - `training/` — Standard-IA at 90 days → Glacier at 180 days (no expiration)
  - `inference/` — Auto-deletes after 30 days

**Path Structure**:
```
artguard-images-raw-dev/
├── training/
│   ├── authentic_v1/
│   │   ├── img001.jpg
│   │   └── img002.jpg
│   └── forged_v1/
│       └── img001.jpg
└── inference/
    ├── 20240207_143022_a1b2c3d4.jpg
    └── 20240207_144531_e5f6g7h8.png
```

**Files**: [terraform/s3.tf](terraform/s3.tf)

---

#### 3c. Images Processed Bucket

**Purpose**: Stores preprocessed training images

**Configuration**:
- **Name**: `artguard-images-processed-{env}`
- **Public access**: Blocked
- **Encryption**: AES-256
- **Versioning**: Disabled
- **Lifecycle**: Standard-IA at 90 days → Glacier at 180 days (no expiration)

**Usage**: Training dataset for model fine-tuning

**Files**: [terraform/s3.tf](terraform/s3.tf)

---

#### 3d. Knowledge Base Bucket

**Purpose**: Stores documentation for Amazon Bedrock RAG

**Configuration**:
- **Name**: `artguard-knowledge-base-{env}`
- **Public access**: Blocked
- **Encryption**: AES-256
- **Versioning**: Enabled (track document updates)
- **Lifecycle**: None

**Content**: Chunked TXT files generated from Met Museum and Wikidata data pipelines (`src/apps/data_pipeline/output/txt/`)

**Upload**: `scripts/upload-rag-data.sh` converts JSONL → chunked TXT, syncs to S3, and triggers Bedrock ingestion

**Bedrock Integration**:
- S3 acts as data source for Knowledge Base
- Bedrock reads docs, creates vector embeddings
- Embeddings stored in OpenSearch Serverless
- RAG retrieves relevant context for Claude prompts

**Files**: [terraform/s3.tf](terraform/s3.tf)

---

### 4. DynamoDB Tables

All 6 tables use on-demand billing, AWS-managed CMK encryption, and PITR enabled in prod only.

#### 4a. Users
- **Name**: `artguard-users-{env}`
- **Hash key**: `user_id`
- **GSI**: `EmailIndex` (hash: `email`) — login/lookup by email

#### 4b. InferenceRecords
- **Name**: `artguard-inference-records-{env}`
- **Hash key**: `inference_id`
- **GSI**: `UserInferencesIndex` (hash: `user_id`, range: `created_at`) — user's inferences sorted by time
- **TTL**: Enabled on `ttl` attribute (auto-cleanup after 90 days)

#### 4c. ImageRecords
- **Name**: `artguard-image-records-{env}`
- **Hash key**: `image_id`
- **GSI**: `LabelSplitIndex` (hash: `label`, range: `split`) — query by label+split

#### 4d. PatchRecords
- **Name**: `artguard-patch-records-{env}`
- **Hash key**: `patch_id`
- **GSI**: `ImagePatchesIndex` (hash: `image_id`, range: `patch_type`) — all patches for an image

#### 4e. RunRecords
- **Name**: `artguard-run-records-{env}`
- **Hash key**: `run_id`
- **GSI1**: `StatusIndex` (hash: `status`, range: `created_at`) — runs by status sorted by time
- **GSI2**: `DatasetVersionIndex` (hash: `dataset_version`, range: `created_at`) — runs by dataset version

#### 4f. ConfigRecords
- **Name**: `artguard-config-records-{env}`
- **Hash key**: `config_id`
- **GSI**: `RunConfigsIndex` (hash: `run_id`, range: `fold_id`) — all configs for a training run

**Files**: [terraform/database.tf](terraform/database.tf)

---

### 5. Amazon Bedrock & OpenSearch

#### 5a. Bedrock Knowledge Base

**Purpose**: Provides Retrieval-Augmented Generation (RAG) for Claude

**Configuration**:
- **Name**: `artguard-knowledge-base-{env}`
- **Model**: Amazon Titan Embeddings V2 (`amazon.titan-embed-text-v2:0`)
- **Vector dimensions**: 1024
- **Data source**: S3 bucket (`artguard-knowledge-base-{env}`)
- **Chunking strategy**: Fixed size (max 300 tokens/chunk dev, 512 prod, 20%/30% overlap)
- **Storage**: OpenSearch Serverless

**Workflow**:
1. **Ingestion**: `upload-rag-data.sh` syncs pipeline output → S3
2. **Embedding**: Bedrock reads S3, creates vector embeddings
3. **Indexing**: Embeddings stored in OpenSearch Serverless
4. **Retrieval**: API queries Bedrock with user question
5. **Ranking**: OpenSearch returns top-k relevant chunks
6. **Generation**: Claude 4.5 Sonnet generates answer with context

**Files**: [terraform/bedrock.tf](terraform/bedrock.tf)

---

#### 5b. OpenSearch Serverless

**Purpose**: Vector database for Knowledge Base embeddings

**Configuration**:
- **Collection name**: `artguard-kb-{env}`
- **Type**: Vectorsearch
- **Index**: `bedrock-knowledge-base-index`
- **Encryption**: AWS-managed key
- **Network**: Public access (AOSS network policy)

**Index Mapping**:
```json
{
  "settings": {"index": {"knn": true, "knn.algo_param.ef_search": 512}},
  "mappings": {
    "properties": {
      "bedrock-knowledge-base-index-vector": {"type": "knn_vector", "dimension": 1024, "method": {"engine": "faiss", "name": "hnsw"}},
      "AMAZON_BEDROCK_TEXT_CHUNK": {"type": "text"},
      "AMAZON_BEDROCK_METADATA": {"type": "text"}
    }
  }
}
```

**Note**: `AMAZON_BEDROCK_METADATA` must be `"text"`, not `"object"`. Using `"object"` causes silent ingestion failures where Bedrock reports COMPLETE with 0 documents indexed.

**Files**: [terraform/bedrock.tf](terraform/bedrock.tf)

---

### 6. CloudFront Distribution

**Purpose**: Global CDN for low-latency frontend and API access

**Configuration**:
- **Price class**: PriceClass_100 (North America + Europe)
- **HTTP version**: HTTP/2
- **IPv6**: Enabled
- **TLS**: TLS 1.2 minimum

**Origins**:
1. **S3 Frontend** (`artguard-frontend-{env}.s3.ca-central-1.amazonaws.com`)
   - Origin access: Origin Access Control (OAC) with SigV4 signing
2. **ALB Backend** (`artguard-backend-alb-{env}.ca-central-1.elb.amazonaws.com`)
   - Origin protocol: HTTP only (ALB terminates HTTPS)

**Cache Behaviors**:
| Path Pattern | Origin | TTL | Notes |
|--------------|--------|-----|-------|
| `/*` (default) | S3 | 0 (no cache) | CloudFront Function rewrites URIs for SPA routing |
| `/api/*` | ALB | 0 (no cache) | Forwards query strings, auth headers, cookies |
| `/static/*` | S3 | 1 year | Hashed filenames, long-term cache |
| `/assets/*` | S3 | 1 year | Images, fonts, etc. |

**Custom Error Pages**:
- 403 → `/index.html` (SPA routing fallback)
- 404 → `/index.html`

**Files**: [terraform/cloudfront.tf](terraform/cloudfront.tf)

---

### 7. VPC & Networking

#### VPC Configuration
- **CIDR**: 10.0.0.0/16 (65,536 IPs)
- **Availability Zones**: 2 (dev) / 3 (prod)
- **DNS hostnames**: Enabled
- **DNS support**: Enabled

#### Subnets

| Type | AZ | CIDR | Resources | Internet Access |
|------|----|----|-----------|-----------------|
| Public | ca-central-1a | 10.0.0.0/24 | ALB, NAT GW | IGW |
| Public | ca-central-1b | 10.0.1.0/24 | ALB, NAT GW | IGW |
| Public | ca-central-1c | 10.0.4.0/24 | ALB, NAT GW (prod) | IGW |
| Private | ca-central-1a | 10.0.2.0/24 | ECS tasks | NAT GW |
| Private | ca-central-1b | 10.0.3.0/24 | ECS tasks | NAT GW |
| Private | ca-central-1c | 10.0.5.0/24 | ECS tasks (prod) | NAT GW |

#### NAT Gateways
- **Quantity**: 2 (dev) / 3 (prod) — one per AZ for high availability
- **Purpose**: Allow private subnet resources to reach internet (Docker pulls, Modal API)

**Files**: [terraform/networking.tf](terraform/networking.tf)

---

### 8. IAM Roles & Policies

#### ECS Task Execution Role
**Purpose**: Pull Docker images from ECR, fetch secrets, write logs
- AWS managed `AmazonECSTaskExecutionRolePolicy` (ECR pull, CloudWatch logs)
- `secretsmanager:GetSecretValue` on Modal API key and JWT secret only
- **Trust policy**: `ecs-tasks.amazonaws.com`

#### ECS Task Role
**Purpose**: Runtime permissions for application code
- DynamoDB: `GetItem`, `PutItem`, `UpdateItem`, `DeleteItem`, `Query`, `Scan`, `BatchGetItem`, `BatchWriteItem` on all 6 tables + indexes
- S3: `GetObject`, `PutObject`, `DeleteObject`, `ListBucket` on images-raw and images-processed buckets
- Bedrock: `InvokeModel`, `InvokeModelWithResponseStream` (Resource: `*`)
- Bedrock KB: `Retrieve`, `RetrieveAndGenerate` on Knowledge Base ARN
- CloudWatch: `logs:CreateLogGroup`, `CreateLogStream`, `PutLogEvents` on ECS log group
- X-Ray: `PutTraceSegments`, `PutTelemetryRecords`, `GetSamplingRules`, `GetSamplingTargets` (conditional: `enable_xray_tracing`)
- ECS Exec: `ssmmessages:CreateControlChannel`, `CreateDataChannel`, `OpenControlChannel`, `OpenDataChannel` (dev only)
- **Trust policy**: `ecs-tasks.amazonaws.com`

#### Bedrock Knowledge Base Role
- S3: `GetObject`, `ListBucket` on knowledge base bucket only
- OpenSearch: `aoss:APIAccessAll` on knowledge base collection only
- Bedrock: `InvokeModel` on `amazon.titan-embed-text-v2:0` model only
- **Trust policy**: `bedrock.amazonaws.com`

**Files**: [terraform/iam.tf](terraform/iam.tf)

---

### 9. Secrets Manager

**Purpose**: Store sensitive credentials securely

| Secret name | Purpose | Value format |
|---|---|---|
| `artguard/modal-api-key-{env}` | Modal GPU inference credentials | `{"token_id":"ak-...","token_secret":"..."}` |
| `artguard/jwt-secret-{env}` | JWT HS256 signing key | Random string (32+ bytes) |

**Configuration**:
- **Encryption**: AWS-managed KMS key
- **Rotation**: Not enabled
- **Recovery window**: 7 days (dev), 30 days (prod)

**Access Control**:
- **ECS Execution Role**: `GetSecretValue` on both secrets (injected as env vars at container start)

**Initial Setup**:
```bash
./scripts/setup-secrets.sh dev   # Dev environment
./scripts/setup-secrets.sh prod  # Production environment
```

**Files**: [terraform/secrets.tf](terraform/secrets.tf)

---

## Architecture Decisions

### 1. Why Both AWS Bedrock and Modal

**Bedrock (Claude 4.5 Sonnet)**:
- Native AWS integration (no VPC egress needed)
- RAG support with Knowledge Base
- High accuracy for general forgery detection
- No cold starts, cost-effective

**Modal (Custom Model)**:
- Specialized forensic analysis
- Faster inference (~2s vs 3-5s)
- Custom fine tuning
- Ensemble with Bedrock for higher explainability

### 2. Why VPC Endpoints Despite Extra Cost

- **Private connectivity**: No internet exposure for AWS API calls
- **Reduced attack surface**: No NAT gateway for AWS services

### 3. Why Auto-Pause Scheduler Only in Dev

- **Cost savings**: $35/mo (10 hours x 30 days)
- **No 24/7 availability needed** in dev
- **Fast resume**: ~2 minutes from cold start
- **Production**: 24/7 availability required for global users

### 4. Why Data Pipeline Shares the Backend ECS

- It's a one-off script, not a long-running service
- Separate ECS services make sense for always-running workloads — not this case
- $0 extra cost — reuses the existing ECS task

### 5. DynamoDB vs RDS

1. Simple relationships: Only 2 foreign keys (user_id, image_id)
2. No complex joins: All "joins" are 1-to-many lookups
3. Known query patterns: All queries can be optimized with GSIs
4. High read/write throughput for image analysis
5. Serverless scaling handles spiky workloads automatically
6. Pay-per-request: Only pay for what we use

---

## Security

### 1. Network Security

- **Private subnets**: ECS tasks have no public IPs
- **Security groups**: Least-privilege ingress/egress rules
- **NAT Gateway**: Controlled internet access for tasks
- **VPC endpoints**: Private AWS service access (no internet)

### 2. IAM Security

All IAM roles follow least-privilege. See [IAM Roles & Policies](#8-iam-roles--policies) for full details.

### 3. Data Security

**Encryption at Rest**:
- **S3**: AES-256 (SSE-S3) on all buckets
- **DynamoDB**: AWS-managed CMK
- **Secrets Manager**: AWS-managed KMS key
- **OpenSearch**: AWS-managed key

**Encryption in Transit**:
- **CloudFront**: TLS 1.2+ enforced
- **ALB → ECS**: HTTP within VPC (private network)
- **ECS → AWS services**: HTTPS via AWS SDK
- **ECS → Modal**: HTTPS required

### 4. Secrets Management

- Modal API Key and JWT Secret stored in Secrets Manager (encrypted)
- Injected as environment variables into ECS tasks via ECS Execution Role

---

## Logging & Structured Metrics

All application logs are emitted as single-line JSON objects to stdout, which the ECS Fargate logging driver forwards to CloudWatch Logs. This structured format enables CloudWatch Logs Insights queries such as filtering by `request_id`, aggregating error rates by endpoint, or computing latency percentiles.

### Log Entry Fields

Each log entry contains:

- **`timestamp`**: ISO 8601 format with millisecond precision
- **`level`**: Standard Python log level (DEBUG, INFO, WARNING, ERROR)
- **`logger`**: Python logger name for source identification
- **`message`**: Human-readable log message
- **`request_id`**: 8-character UUID prefix, generated per-request or extracted from the inbound `X-Request-ID` header
- **`user_id`**: Authenticated user's ID (empty for unauthenticated requests)
- **`source`**: File path and line number (included only for WARNING and above to reduce log volume)
- **`exc_info`**: Full exception traceback (included only when an exception is being handled)

The `request_id` and `user_id` are stored in Python `ContextVar` instances, which are async-safe and scoped to the current request without thread-local state. The `RequestLoggingMiddleware` sets these context variables at the start of each request and resets them after the response is sent.

### CloudWatch Embedded Metric Format (EMF)

Custom application metrics are emitted using CloudWatch Embedded Metric Format (EMF), which embeds metric data directly in log entries. When CloudWatch Logs receives an EMF-formatted log line, it automatically extracts and publishes the metric to CloudWatch Metrics without requiring explicit `PutMetricData` API calls:

- **`InferenceLatency`** (Seconds): End-to-end Modal inference duration
- **`RAGLatency`** (Seconds): Bedrock RetrieveAndGenerate call duration
- **`InferenceSuccess`** / **`InferenceError`** (Count): Success and failure counters
- **`RAGError`** (Count): Bedrock call failure counter

### CloudWatch Log Metric Filters

Three CloudWatch Log Metric Filters extract additional operational signals:
- **`ApplicationErrors`**: matches `$.level = "ERROR"`
- **`ApplicationWarnings`**: matches `$.level = "WARNING"`
- **`AuthFailures`**: matches `$.status = 401`

These are published to the "ArtGuard" CloudWatch namespace and drive the alarm for error log volume spikes.

---

## Monitoring & Observability

### CloudWatch Logs

**ECS Tasks**:
- **Log group**: `/ecs/artguard-backend`
- **Retention**: 7 days (dev), 30 days (prod)
- **Contents**: Structured JSON application logs, errors, request traces

### X-Ray Distributed Tracing

**Status**: Disabled (dev), Enabled (prod)

In production, AWS X-Ray distributed tracing visualizes request flows across ECS, Bedrock, and DynamoDB. Controlled via `var.enable_xray_tracing`.

### Container Insights

**Status**: Enabled in both environments

**Metrics collected**:
- Container CPU/memory at task level
- Network I/O (bytes sent/received)
- Storage I/O (ephemeral disk)
- Task restart count

### CloudWatch Dashboard

**Dashboard name**: `artguard-dashboard`

A unified operational view across six widget rows:

1. **ECS CPU and Memory** — CPU utilization, memory utilization, running task count (5-min intervals)
2. **ALB Request & Success Metrics** — Total request count, 2xx successful responses (5-min intervals)
3. **ALB Error Metrics** — 4xx client errors, 5xx server errors (5-min intervals)
4. **API Latency** — Average and p99 latency alongside custom application metrics for inference and RAG latency
5. **DynamoDB Consumed Capacity** — Read/write capacity units consumed across all 6 tables (5-min intervals)
6. **S3 Bucket Size** — Bucket size in bytes across all 4 buckets (daily intervals)

### CloudWatch Alarms

Seven CloudWatch alarms detect operational anomalies:

1. ALB 5xx errors exceeding 10 in 5 minutes
2. p99 latency above 10 seconds
3. ECS CPU utilization above 85%
4. ECS memory utilization above 85%
5. Fewer than one healthy ALB target
6. DynamoDB throttling events
7. Application error log volume exceeding 20 entries in 5 minutes

**Files**: [terraform/monitoring.tf](terraform/monitoring.tf)

---

## Cost Management

### Implemented Cost Optimizations

#### 1. Dev Auto-Pause Scheduler
ECS service scales to 0 tasks at 10 PM EST, resumes at 8 AM EST (dev only). Saves ~14 hours/day of compute costs.

#### 2. DynamoDB On-Demand Billing
All 6 tables use `PAY_PER_REQUEST` billing. No wasted provisioned capacity during low usage.

#### 3. S3 Lifecycle Policies
- `images-raw/training/` — Standard-IA at 30 days (dev) / 90 days (prod) → Glacier at 180 days
- `images-raw/inference/` — Auto-deletes after 7 days (dev) / 30 days (prod)
- `images-processed/` — Standard-IA at 90 days → Glacier at 180 days

#### 4. CloudWatch Log Retention
7 days (dev), 30 days (prod) instead of indefinite retention.

#### 5. S3 Gateway Endpoint (Free)
S3 traffic from private subnets uses the free Gateway Endpoint instead of NAT Gateway, avoiding data transfer charges.

### Estimated Costs

| Service | Monthly Cost | Notes |
|---------|-------------|-------|
| ECS Fargate | $15-25 | 1 vCPU, 2 GB, auto-paused 10 hrs/day |
| NAT Gateway | $35-45 | Largest fixed cost |
| DynamoDB | $1-5 | On-demand billing, low volume |
| S3 | $1-3 | Small dataset, lifecycle tiering |
| OpenSearch Serverless | $0 idle | Scales to zero in dev |
| CloudFront | $0-1 | Free tier covers low traffic |
| Modal (inference) | $0.01-0.05/req | T4 at $0.59/hr, pay-per-second |
| Modal (training) | $2-8/run | A10G at $1.10/hr |

### Scaling to Production

- **Compute**: ECS auto-scaling (2-10 tasks in prod) absorbs traffic spikes. Modal serverless GPUs auto-scale with no pre-provisioned capacity.
- **Database**: DynamoDB on-demand scales transparently to thousands of RPS. GSI-optimized queries ensure single-digit-ms latency regardless of table size.
- **Storage**: S3 scales to exabytes. Lifecycle policies keep cost proportional to active data volume.
- **CDN**: CloudFront's global edge network absorbs frontend traffic. Static assets cached for one year.

---

## Disaster Recovery

ArtGuard implements a script-driven disaster recovery mechanism using Terraform's `state rm` and `import` commands to enable infrastructure destruction with full data preservation.

During a simulated disaster, `destroy-all.sh --preserve-data` detaches all data-bearing resources — six DynamoDB tables and two S3 data buckets (raw images and knowledge base) — from Terraform state before destroying the remaining infrastructure. These resources survive in AWS as orphans, invisible to Terraform but fully intact with all data preserved.

Recovery is executed via `recover-prod.sh`, which re-imports the orphaned resources into Terraform state, runs `terraform apply` to recreate all stateless infrastructure (VPC, ECS, ALB, CloudFront, OpenSearch, IAM roles), rebuilds and pushes the Docker image, deploys the backend to ECS, and re-triggers Bedrock Knowledge Base ingestion from the surviving S3 documents. OpenSearch vector embeddings are the only artifacts rebuilt during recovery; no user data, inference records, training images, or RAG source documents are lost.

The entire disaster recovery cycle — destruction, verification that data survives, and full recovery — is executable via a single command (`disaster-recovery.sh`) for demonstration purposes.

For full details including manual recovery steps and post-recovery verification, see [DISASTER_RECOVERY.md](../DISASTER_RECOVERY.md).

---

## Environment Differences

### Dev vs Prod Configuration

| Setting | Dev | Prod | Rationale |
|---------|-----|------|-----------|
| **ECS Tasks** | 1-5 | 2-10 | Prod needs higher capacity. Auto-scaling on CPU/memory/requests. |
| **Task CPU** | 1 vCPU | 2 vCPU | Prod handles more concurrent requests. |
| **Task Memory** | 2 GB | 4 GB | Prod caches more in memory. |
| **Min Capacity** | 1 | 2 | Prod maintains 2 tasks for zero-downtime deploys. |
| **Auto-Pause** | Enabled | Disabled | Dev doesn't need 24/7 availability. |
| **VPC Endpoints** | Enabled | Enabled | Security over cost in both environments. |
| **NAT Gateways** | 2 | 3 | One per AZ (2 AZs dev, 3 AZs prod). |
| **DynamoDB PITR** | Disabled | Enabled | Point-in-time recovery for prod data. |
| **Log Retention** | 7 days | 30 days | Prod keeps logs longer for audits. |
| **Container Insights** | Enabled | Enabled | Enabled in both. |
| **X-Ray Tracing** | Disabled | Enabled | Prod has distributed tracing. |

| Metric | Dev | Prod | Notes |
|--------|-----|------|-------|
| **Max RPS** | ~50 | ~200 | Assuming 5s avg response time |
| **Cold start** | ~60s | ~30s | Time from 0 tasks to healthy |
