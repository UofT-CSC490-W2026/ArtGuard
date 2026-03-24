# ArtGuard Data Architecture

DynamoDB schemas, S3 storage structure, and data workflows.

---

## Table of Contents

1. [DynamoDB Tables](#dynamodb-tables)
2. [S3 Storage Structure](#s3-storage-structure)
3. [Data Workflows](#data-workflows)
4. [Useful Commands](#useful-commands)

---

## DynamoDB Tables

All tables use on-demand (PAY_PER_REQUEST) billing. Table names follow the pattern `artguard-{name}-{env}`.

### Table 1: Users (`artguard-users-{env}`)

User accounts and authentication.

| Attribute | Type | Key | Description |
|-----------|------|-----|-------------|
| `user_id` | String | **PK** | UUID |
| `email` | String | GSI-PK | Stored lowercase for case-insensitive lookup |
| `username` | String | - | Display name |
| `password_hash` | String | - | bcrypt hash |
| `created_at` | Number | - | Unix ms timestamp |
| `updated_at` | Number | - | Unix ms timestamp (set on profile/password updates) |

**GSI: EmailIndex** — `email` (PK). Used for login-by-email queries.

---

### Table 2: InferenceRecords (`artguard-inference-records-{env}`)

Forgery detection results from user uploads.

| Attribute | Type | Key | Description |
|-----------|------|-----|-------------|
| `inference_id` | String | **PK** | UUID |
| `user_id` | String | GSI-PK | Foreign key to Users |
| `created_at` | Number | GSI-SK | Unix ms timestamp |
| `image_id` | String | - | Foreign key to ImageRecords |
| `image_name` | String | - | Original filename |
| `image_path` | String | - | S3 URI of raw upload |
| `artist_name` | String | - | Artist name from upload form |
| `artwork_name` | String | - | Artwork title from upload form |
| `title` | String | - | Same as artwork_name (legacy compat) |
| `file_size` | Number | - | Upload size in bytes |
| `score` | Number | - | Mean patch probability (0.0–1.0) |
| `prediction` | Number | - | 1=authentic, 0=forgery, -1=pending |
| `inference_status` | String | - | `processing`, `completed`, `failed` |
| `explanation` | String | - | RAG-generated explanation text |
| `error_message` | String | - | Error detail (only if failed) |
| `ttl` | Number | - | DynamoDB TTL (Unix seconds, default 90 days) |

**GSI: UserInferencesIndex** — `user_id` (PK), `created_at` (SK). Used for paginated inference history.

---

### Table 3: ImageRecords (`artguard-image-records-{env}`)

Dataset images for training, evaluation, and inference.

| Attribute | Type | Key | Description |
|-----------|------|-----|-------------|
| `image_id` | String | **PK** | UUID (derived from S3 key path) |
| `image_name` | String | - | Filename |
| `image_path` | String | - | S3 URI |
| `image_width` | Number | - | Width in pixels (clamped >= 0) |
| `image_height` | Number | - | Height in pixels (clamped >= 0) |
| `label` | String | - | `authentic` or `inauthentic` |
| `sublabel` | String | - | `original`, `forgery`, `imitation`, or `proxy` |
| `split` | String | - | `train`, `val`, `test`, or `unassigned` |
| `fold_id` | Number | - | Outer cross-validation fold (0-indexed) |
| `run_id` | String | - | Processing run that created/updated this record |
| `attributed_creator` | String | - | Artist the artwork is attributed to |
| `actual_creator` | String | - | True creator |
| `created_at` | Number | - | Unix ms timestamp |

---

### Table 4: PatchRecords (`artguard-patch-records-{env}`)

224x224 image patches extracted for model input.

| Attribute | Type | Key | Description |
|-----------|------|-----|-------------|
| `patch_id` | String | **PK** | UUID |
| `image_id` | String | - | Foreign key to ImageRecords |
| `patch_path` | String | - | S3 URI of the patch image |
| `patch_type` | String | - | `grid`, `center_crop_orig`, `center_crop_down_2x`, etc. |
| `patch_x` | Number | - | X offset in source image |
| `patch_y` | Number | - | Y offset in source image |
| `patch_width` | Number | - | Patch width (always 224) |
| `patch_height` | Number | - | Patch height (always 224) |
| `score` | Number | - | Per-patch probability (set after inference) |
| `prediction` | Number | - | Per-patch 0/1 prediction (set after inference) |
| `created_at` | Number | - | Unix ms timestamp |

---

### Table 5: RunRecords (`artguard-run-records-{env}`)

Training and data processing run metadata.

| Attribute | Type | Key | Description |
|-----------|------|-----|-------------|
| `run_id` | String | **PK** | UUID |
| `created_at` | Number | - | Unix ms timestamp |
| `status` | String | - | `running`, `completed`, `completed_with_errors`, `failed` |
| `k_folds` | Number | - | Number of cross-validation folds (default: 5) |
| `stratify_on` | String | - | Stratification field (default: `sublabel`) |
| `outer_split_seed` | Number | - | Seed for outer fold assignment (default: 17) |
| `inner_split_seed` | Number | - | Seed for inner train/val split (default: 99) |
| `mean_accuracy` | Number | - | Mean accuracy across folds |
| `mean_f1` | Number | - | Mean F1 across folds |

---

### Table 6: ConfigRecords (`artguard-config-records-{env}`)

Per-fold hyperparameter configurations and training results.

| Attribute | Type | Key | Description |
|-----------|------|-----|-------------|
| `config_id` | String | **PK** | UUID |
| `run_id` | String | - | Foreign key to RunRecords |
| `fold_id` | Number | - | Fold number (0-indexed) |
| `hyperparameters` | Map | - | `{lr, batch_size, ...}` |
| `best_epoch` | Number | - | Epoch with best validation metric |
| `early_stopped` | Boolean | - | Whether training was early-stopped |
| `is_best_in_fold` | Boolean | - | Best config in this fold |
| `created_at` | Number | - | Unix ms timestamp |

---

## S3 Storage Structure

### Buckets

| Bucket | Purpose | Lifecycle |
|--------|---------|-----------|
| `artguard-images-raw-{env}` | Original uploaded images (inference + training) | 30-day expiry on inference prefix |
| `artguard-images-processed-{env}` | 224x224 patches for model input | 90-day expiry |
| `artguard-frontend-{env}` | React/Vite static assets | None (served via CloudFront) |
| `artguard-knowledge-base-{env}` | RAG text documents for Bedrock KB | Versioning enabled |

### Key Structure

```
artguard-images-raw-{env}/
├── inference/{image_id}/{filename}       # User uploads via POST /inference
└── training/unprocessed/{image_id}/      # Training images uploaded via scripts

artguard-images-processed-{env}/
└── inference/{image_id}/                 # 224x224 patches created by preprocess.py
    ├── grid_0_0.jpg
    ├── grid_0_1.jpg
    ├── center_crop_orig.jpg
    └── center_crop_down_2x.jpg

artguard-knowledge-base-{env}/
└── *.txt                                # Met Museum + Wikidata RAG documents
```

**Terraform:** [infra/terraform/s3.tf](infra/terraform/s3.tf)

### Data Lake Tiers (Bronze / Silver / Gold)

Our S3 storage follows a medallion architecture pattern across two data domains:

#### Image Pipeline

| Tier | What | Where | Example |
|------|------|-------|---------|
| **Bronze** | Raw uploaded images (unmodified user uploads and training images) | `artguard-images-raw-{env}/` | `inference/{image_id}/painting.jpg` |
| **Silver** | 224x224 patches extracted from raw images (resized, cropped, normalized) | `artguard-images-processed-{env}/` | `inference/{image_id}/grid_0_0.jpg` |
| **Gold** | Forgery decision (prediction, score, explanation) stored in DynamoDB | `artguard-inference-records-{env}` (DynamoDB) | `{prediction: 1, score: 0.87, explanation: "..."}` |

#### RAG Pipeline

| Tier | What | Where | Example |
|------|------|-------|---------|
| **Bronze** | Raw API responses from Met Museum CSV and Wikidata SPARQL | Not stored — fetched on-demand during pipeline runs | Met CSV rows, Wikidata JSON bindings |
| **Silver** | Cleaned and structured text documents (JSONL → chunked TXT) | `artguard-knowledge-base-{env}/` | `met_data_part1.txt`, `wikidata_data.txt` |
| **Gold** | RAG explanations generated by Bedrock (Claude + Knowledge Base) | `artguard-inference-records-{env}` (DynamoDB `explanation` field) | `"The model detected characteristics consistent with..."` |

**Note on RAG Bronze data:** We do not persist the raw Met Museum CSV or Wikidata SPARQL responses in S3. The pipelines fetch from the public APIs and write directly to the Silver tier. Ideally the raw responses would be stored for reproducibility and audit trails, but we chose not to due to storage costs and the fact that the source APIs are publicly accessible and deterministic — the same queries produce the same results. The pipeline scripts (`met_pipeline.py`, `wikidata_pipeline.py`) can be re-run at any time to regenerate the Silver data from source.

### Partitioning Strategy

Data is partitioned across 4 S3 buckets, separated by purpose, access pattern, and lifecycle policy:

| Bucket | Tier | Partitioning | Lifecycle | Why Separate |
|--------|------|-------------|-----------|--------------|
| `artguard-images-raw-{env}` | Bronze | `{use_case}/{image_id}/{filename}` where use_case is `inference/` or `training/unprocessed/` | 30-day expiry on inference prefix | Raw uploads need short retention (user images are transient); training images persist longer |
| `artguard-images-processed-{env}` | Silver | `{use_case}/{image_id}/{patch_name}.jpg` | 90-day expiry | Patches are derived data — can be regenerated from raw images, so shorter retention is safe |
| `artguard-knowledge-base-{env}` | Silver | Flat namespace (`*.txt`) | Versioning enabled, no expiry | Bedrock Knowledge Base requires a dedicated S3 data source; versioning enables rollback if bad documents are ingested |
| `artguard-frontend-{env}` | N/A | Vite build output (`index.html`, `assets/`) | No expiry | Static assets served via CloudFront; separate bucket avoids accidental deletion by data lifecycle policies |

**Why 4 buckets instead of 1 with prefixes?**
- **Different lifecycle policies**: Raw inference images expire in 30 days, patches in 90 days, RAG documents never expire. S3 lifecycle rules apply per-prefix but separate buckets make policies explicit and prevent accidental data loss.
- **Different access patterns**: The frontend bucket is public via CloudFront OAI; all other buckets are private. Mixing public and private data in one bucket increases the blast radius of misconfigured bucket policies.
- **Bedrock requirement**: AWS Bedrock Knowledge Base requires a dedicated S3 bucket as its data source — it cannot share a bucket with other data.
- **IAM least privilege**: Each bucket has its own IAM policy. The ECS task role can read/write image buckets but has no access to the frontend bucket. CloudFront can read the frontend bucket but not the image buckets.

---

## Data Workflows

### Workflow 1: Real-Time Inference

User uploads an image via the frontend; the backend orchestrates the full pipeline.

```
1. User uploads image via POST /inference
   (artist_name, artwork_name, file <= 20 MB)
   ↓
2. Backend validates input, opens with PIL, converts to RGB
   ↓
3. Upload raw image to S3 (inference/{image_id}/{filename})
   Write ImageRecord + InferenceRecord to DynamoDB (status=processing, prediction=-1)
   ↓
4. Split image into 224x224 patches (preprocess.py)
   Grid patches + center crops at multiple scales
   Upload patches to S3 processed bucket
   Write PatchRecords to DynamoDB
   ↓
5. Send patch S3 URIs to Modal (Swin Transformer inference)
   Returns per-patch probabilities + painting-level prediction
   ↓
6. Query Bedrock Knowledge Base (RAG) for explanation
   Prompt includes prediction result + confidence score
   ↓
7. Update InferenceRecord (status=completed, score, prediction, explanation)
   Update PatchRecords with per-patch scores
   ↓
8. Return result to user
   {inference_id, prediction, score, explanation, image_url}
```

**Implementation:** [inference_router.py](src/apps/backend/routes/inference_router.py) → [inference_service.py](src/apps/backend/services/inference_service.py) → [preprocess.py](src/apps/data_pipeline/preprocess.py)

---

### Workflow 2: Training Data Upload

Upload local images to S3 and write metadata to DynamoDB for model training.

```
1. Run upload script from repo root
   ./scripts/update-data.sh --data-dir ./data --metadata ./data/metadata.csv
   ↓
2. For each image in metadata CSV:
   Upload to s3://artguard-images-raw-{env}/training/unprocessed/{image_id}/
   Write ImageRecord to DynamoDB (label, sublabel, creator from CSV)
   ↓
3. Trigger data processing (POST /process_data or manual)
   Spawns ECS Fargate task running driver.py
   ↓
4. Driver processes each unprocessed image:
   Download from S3 → split into patches → upload patches → write PatchRecords
   Mark ImageRecord as processed
   ↓
5. Training data ready for Modal
   PatchDataset (dataset.py) reads from DynamoDB + S3 at training time
```

**Implementation:** [update-data.sh](scripts/update-data.sh) → [driver.py](src/apps/data_pipeline/driver.py) → [preprocess.py](src/apps/data_pipeline/preprocess.py)

---

### Workflow 3: RAG Knowledge Base Update

Update the Bedrock Knowledge Base with Met Museum and Wikidata documents.

```
1. Run data pipelines to generate JSONL
   python -m src.apps.data_pipeline.met_pipeline
   python -m src.apps.data_pipeline.wikidata_pipeline
   ↓
2. Convert JSONL to chunked TXT files (max 500 records per file)
   python scripts/convert-jsonl-to-txt.py
   ↓
3. Upload TXT files to S3 knowledge base bucket
   ./scripts/upload-rag-data.sh
   ↓
4. Trigger Bedrock ingestion job
   Documents → OpenSearch Serverless (vector embeddings)
   ↓
5. RAG queries now return relevant context from the knowledge base
```

**Implementation:** [met_pipeline.py](src/apps/data_pipeline/met_pipeline.py), [wikidata_pipeline.py](src/apps/data_pipeline/wikidata_pipeline.py) → [upload-rag-data.sh](scripts/upload-rag-data.sh)

---

## Useful Commands

### Get Table Names from Terraform

```bash
terraform -chdir=infra/terraform output -raw dynamodb_users_table_name
terraform -chdir=infra/terraform output -raw dynamodb_inference_records_table_name
terraform -chdir=infra/terraform output -raw dynamodb_image_records_table_name
terraform -chdir=infra/terraform output -raw dynamodb_patch_records_table_name
terraform -chdir=infra/terraform output -raw dynamodb_run_records_table_name
terraform -chdir=infra/terraform output -raw dynamodb_config_records_table_name
```

### Query Tables

```bash
# List all tables
aws dynamodb list-tables --region ca-central-1

# Get item count
aws dynamodb scan \
  --table-name artguard-inference-records-dev \
  --select COUNT \
  --region ca-central-1

# Query user's inferences (GSI)
aws dynamodb query \
  --table-name artguard-inference-records-dev \
  --index-name UserInferencesIndex \
  --key-condition-expression "user_id = :uid" \
  --expression-attribute-values '{":uid":{"S":"user-123"}}' \
  --region ca-central-1
```
