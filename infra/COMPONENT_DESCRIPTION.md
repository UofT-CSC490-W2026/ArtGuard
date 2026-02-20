## Comprehensive Component Breakdown

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
DYNAMODB_TABLE_NAME=<image_analysis table name>  # NOTE: references aws_dynamodb_table.image_analysis which doesn't exist in database.tf — needs fixing in app.tf
KNOWLEDGE_BASE_ID=<bedrock knowledge base ID>
MODAL_API_KEY=<from-secrets-manager>  # injected via ECS secrets (Execution Role), not environment
AWS_XRAY_TRACING_ENABLED=false
```

**IAM Permissions** (ECS Task Role):
- `dynamodb:GetItem`, `PutItem`, `UpdateItem`, `DeleteItem`, `Query`, `Scan`, `BatchGetItem`, `BatchWriteItem` on all 6 tables + indexes
- `s3:GetObject`, `PutObject`, `DeleteObject`, `ListBucket` on images-raw and images-processed buckets
- `bedrock:InvokeModel`, `InvokeModelWithResponseStream` (Resource: `*`)
- `bedrock:Retrieve`, `RetrieveAndGenerate` on Knowledge Base ARN
- `logs:CreateLogGroup`, `CreateLogStream`, `PutLogEvents` on ECS log group
- `xray:PutTraceSegments`, `PutTelemetryRecords`, `GetSamplingRules`, `GetSamplingTargets`, `GetSamplingStatisticSummaries` (if `enable_xray_tracing = true`)
- `ssmmessages:CreateControlChannel`, `CreateDataChannel`, `OpenControlChannel`, `OpenDataChannel` (dev only, for ECS Exec)

**IAM Permissions** (ECS Execution Role):
- AWS managed `AmazonECSTaskExecutionRolePolicy` (ECR pull, CloudWatch logs)
- `secretsmanager:GetSecretValue` on Modal API key secret only

**Files**:
- Task definition: [infra/terraform/app.tf:1-80](infra/terraform/app.tf#L1-L80)
- Service: [infra/terraform/app.tf:82-130](infra/terraform/app.tf#L82-L130)
- Auto-scaling: [infra/terraform/app.tf:250-356](infra/terraform/app.tf#L250-L356)

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

**Files**: [infra/terraform/app.tf:132-248](infra/terraform/app.tf#L132-L248)

---

### 4. S3 Buckets

#### 4a. Frontend Bucket

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

**CloudFront**: Origin for `/*` path pattern

**Files**: [infra/terraform/s3.tf:1-50](infra/terraform/s3.tf#L1-L50)

---

#### 4b. Images Raw Bucket

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

**IAM Access**:
- ECS tasks: `s3:GetObject`, `PutObject`, `DeleteObject`, `ListBucket`

**Files**: [infra/terraform/s3.tf:52-150](infra/terraform/s3.tf#L52-L150)

---

#### 4c. Images Processed Bucket

**Purpose**: Stores preprocessed training images

**Configuration**:
- **Name**: `artguard-images-processed-{env}`
- **Public access**: Blocked
- **Encryption**: AES-256
- **Versioning**: Disabled
- **Lifecycle**: Standard-IA at 90 days → Glacier at 180 days (no expiration)

**Path Structure**:
```
artguard-images-processed-dev/
└── processed/
    ├── authentic_v1/
    │   ├── img001.jpg  (normalized, RGB, 2048px max)
    │   └── img002.jpg
    └── forged_v1/
        └── img001.jpg
```

**Usage**: Training dataset for model fine-tuning

**Files**: [infra/terraform/s3.tf:152-250](infra/terraform/s3.tf#L152-L250)

---

#### 4d. Knowledge Base Bucket

**Purpose**: Stores documentation for Amazon Bedrock RAG

**Configuration**:
- **Name**: `artguard-knowledge-base-{env}`
- **Public access**: Blocked
- **Encryption**: AES-256
- **Versioning**: Enabled (track document updates)
- **Lifecycle**: None

**Content**: Markdown documentation from `docs/` directory

**Upload**: `scripts/update-knowledge-base.sh` syncs `docs/` → S3 → Bedrock ingestion

**Bedrock Integration**:
- S3 acts as data source for Knowledge Base
- Bedrock reads docs, creates vector embeddings
- Embeddings stored in OpenSearch Serverless
- RAG retrieves relevant context for Claude prompts


**Files**: [infra/terraform/s3.tf:252-350](infra/terraform/s3.tf#L252-L350)

---

### 5. DynamoDB Tables

All 6 tables use on-demand billing, AWS-managed CMK encryption, and PITR enabled in prod only.

#### 5a. Users

- **Name**: `artguard-users-{env}`
- **Hash key**: `user_id`
- **GSI**: `EmailIndex` (hash: `email`) — login/lookup by email

**Files**: [infra/terraform/database.tf:4-41](infra/terraform/database.tf#L4-L41)

---

#### 5b. InferenceRecords

- **Name**: `artguard-inference-records-{env}`
- **Hash key**: `inference_id`
- **GSI**: `UserInferencesIndex` (hash: `user_id`, range: `created_at`) — user's inferences sorted by time
- **TTL**: Enabled on `ttl` attribute (auto-cleanup after 90 days)

**Files**: [infra/terraform/database.tf:43-90](infra/terraform/database.tf#L43-L90)

---

#### 5c. ImageRecords

- **Name**: `artguard-image-records-{env}`
- **Hash key**: `image_id`
- **GSI**: `LabelSplitIndex` (hash: `label`, range: `split`) — query by label+split (e.g., all "authentic" images in "train" set)

**Files**: [infra/terraform/database.tf:92-133](infra/terraform/database.tf#L92-L133)

---

#### 5d. PatchRecords

- **Name**: `artguard-patch-records-{env}`
- **Hash key**: `patch_id`
- **GSI**: `ImagePatchesIndex` (hash: `image_id`, range: `patch_type`) — all patches for an image

**Files**: [infra/terraform/database.tf:135-176](infra/terraform/database.tf#L135-L176)

---

#### 5e. RunRecords

- **Name**: `artguard-run-records-{env}`
- **Hash key**: `run_id`
- **GSI1**: `StatusIndex` (hash: `status`, range: `created_at`) — runs by status sorted by time
- **GSI2**: `DatasetVersionIndex` (hash: `dataset_version`, range: `created_at`) — runs by dataset version

**Files**: [infra/terraform/database.tf:178-233](infra/terraform/database.tf#L178-L233)

---

#### 5f. ConfigRecords

- **Name**: `artguard-config-records-{env}`
- **Hash key**: `config_id`
- **GSI**: `RunConfigsIndex` (hash: `run_id`, range: `fold_id`) — all configs for a training run

**Files**: [infra/terraform/database.tf:235-277](infra/terraform/database.tf#L235-L277)

---

### 6. Amazon Bedrock & OpenSearch

#### 6a. Bedrock Knowledge Base

**Purpose**: Provides Retrieval-Augmented Generation (RAG) for Claude

**Configuration**:
- **Name**: `artguard-knowledge-base-{env}`
- **Model**: Amazon Titan Embeddings G1 (text-embedding-ada-002 equivalent)
- **Vector dimensions**: 1536
- **Data source**: S3 bucket (`artguard-knowledge-base-{env}`)
- **Chunking strategy**: Fixed size (max 300 tokens/chunk dev, 512 prod, 20%/30% overlap)
- **Storage**: OpenSearch Serverless

**Workflow**:
1. **Ingestion**: `update-knowledge-base.sh` syncs docs → S3
2. **Embedding**: Bedrock reads S3, creates vector embeddings
3. **Indexing**: Embeddings stored in OpenSearch Serverless
4. **Retrieval**: API queries Bedrock with user question
5. **Ranking**: OpenSearch returns top-k relevant chunks
6. **Generation**: Claude 3.5 Sonnet generates answer with context

**Use Cases**:
- Answer questions about ArtGuard architecture
- Provide code examples from documentation
- Explain infrastructure components

**Files**: [infra/terraform/bedrock.tf](infra/terraform/bedrock.tf)

---

#### 6b. OpenSearch Serverless

**Purpose**: Vector database for Knowledge Base embeddings

**Configuration**:
- **Collection name**: `artguard-kb-{env}`
- **Type**: Vectorsearch
- **Index**: `bedrock-knowledge-base-default-index`
- **Replicas**: 2 (high availability)
- **Encryption**: AWS-managed key
- **Network**: VPC access only

**Index Mapping**:
```json
{
  "mappings": {
    "properties": {
      "vector": {"type": "knn_vector", "dimension": 1536},
      "text": {"type": "text"},
      "metadata": {"type": "object"}
    }
  }
}
```

**IAM Access**:
- Bedrock service: `aoss:CreateIndex`, `BatchGetCollection`, `APIAccessAll`
- ECS tasks: `aoss:APIAccessAll` (for hybrid search if needed)

**Files**: [infra/terraform/bedrock.tf:50-150](infra/terraform/bedrock.tf#L50-L150)

---

### 7. CloudFront Distribution

**Purpose**: Global CDN for low-latency frontend and API access

**Configuration**:
- **Price class**: PriceClass_100 (North America + Europe)
- **HTTP version**: HTTP/2
- **IPv6**: Enabled
- **TLS**: TLS 1.2 minimum
- **Logging**: Disabled (enable in prod for security audits)

**Origins**:
1. **S3 Frontend** (`artguard-frontend-{env}.s3.ca-central-1.amazonaws.com`)
   - Origin access: Origin Access Control (OAC) with SigV4 signing
   - Custom headers: None
2. **ALB Backend** (`artguard-backend-alb-{env}.ca-central-1.elb.amazonaws.com`)
   - Origin protocol: HTTP only (ALB terminates HTTPS)
   - Custom headers: None

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

**Files**: [infra/terraform/cloudfront.tf](infra/terraform/cloudfront.tf)

---

### 8. VPC & Networking

#### VPC Configuration

- **CIDR**: 10.0.0.0/16 (65,536 IPs)
- **Availability Zones**: 2 (ca-central-1a, ca-central-1b)
- **DNS hostnames**: Enabled
- **DNS support**: Enabled

#### Subnets

| Type | AZ | CIDR | Resources | Internet Access |
|------|----|----|-----------|-----------------|
| Public | ca-central-1a | 10.0.0.0/24 | ALB, NAT GW | IGW |
| Public | ca-central-1b | 10.0.1.0/24 | ALB, NAT GW | IGW |
| Private | ca-central-1a | 10.0.2.0/24 | ECS tasks | NAT GW |
| Private | ca-central-1b | 10.0.3.0/24 | ECS tasks | NAT GW |

#### NAT Gateways

- **Quantity**: 2 (one per AZ for high availability)
- **Purpose**: Allow private subnet resources to reach internet (Docker pulls, Modal API)

**Files**: [infra/terraform/networking.tf](infra/terraform/networking.tf)

---

### 9. IAM Roles & Policies

#### ECS Task Execution Role

**Purpose**: Pull Docker images from ECR, fetch secrets, write logs

**Permissions**:
- `ecr:GetAuthorizationToken`, `BatchCheckLayerAvailability`, `GetDownloadUrlForLayer`, `BatchGetImage`
- `logs:CreateLogStream`, `PutLogEvents`
- `secretsmanager:GetSecretValue` (Modal API key)

**Trust policy**: `ecs-tasks.amazonaws.com`

---

#### ECS Task Role

**Purpose**: Runtime permissions for application code

**Permissions**:
- DynamoDB: `GetItem`, `PutItem`, `UpdateItem`, `DeleteItem`, `Query`, `Scan`, `BatchGetItem`, `BatchWriteItem` on all 6 tables + indexes
- S3: `GetObject`, `PutObject`, `DeleteObject`, `ListBucket` on images-raw and images-processed buckets
- Bedrock: `InvokeModel`, `InvokeModelWithResponseStream` (Resource: `*`)
- Bedrock KB: `Retrieve`, `RetrieveAndGenerate` on Knowledge Base ARN
- CloudWatch: `logs:CreateLogGroup`, `CreateLogStream`, `PutLogEvents` on ECS log group
- X-Ray: `PutTraceSegments`, `PutTelemetryRecords`, `GetSamplingRules`, `GetSamplingTargets`, `GetSamplingStatisticSummaries` (conditional: `enable_xray_tracing`)
- ECS Exec: `ssmmessages:CreateControlChannel`, `CreateDataChannel`, `OpenControlChannel`, `OpenDataChannel` (conditional: dev only)

**Trust policy**: `ecs-tasks.amazonaws.com`

---

#### Bedrock Knowledge Base Role

**Permissions**:
- S3: `GetObject`, `ListBucket` on knowledge base bucket only
- OpenSearch: `aoss:APIAccessAll` on knowledge base collection only
- Bedrock: `InvokeModel` on `amazon.titan-embed-text-v1` model only

**Trust policy**: `bedrock.amazonaws.com`

**Files**: [infra/terraform/iam.tf](infra/terraform/iam.tf)

---

### 10. Secrets Manager

**Purpose**: Store Modal API key securely

**Configuration**:
- **Secret name**: `artguard/modal-api-key-{env}`
- **Encryption**: AWS-managed KMS key
- **Rotation**: Not enabled (API key)
- **Recovery window**: 7 days (dev), 30 days (prod)

**Secret value**:
```json
{
  "api_key": "modal-xxxxxxxxxxxxx"
}
```

**Access Control** (resource-based policy):
- **Allow**: ECS Execution Role (`GetSecretValue`, `DescribeSecret`)
- **Allow**: Account root (full access for rotation)
- **Deny**: All other principals (`GetSecretValue`)

**Initial Setup**:
```bash
# Dev environment
./scripts/setup-secrets.sh dev

# Production environment
./scripts/setup-secrets.sh prod
```
**Files**: [infra/terraform/secrets.tf](infra/terraform/secrets.tf)

---
